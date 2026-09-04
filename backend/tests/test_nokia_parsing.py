"""The live adapter's response parsing, fed malformed payloads directly.

No network and no client instance: every function under test takes a decoded JSON body
and returns a value or raises. That is the point of the split — these are the shapes the
sandbox could hand us on stage, and each one used to resolve to a confident wrong answer
instead of an error.

The through-line of every test here: a body we cannot read must raise, because
``FallbackNaCClient`` catches exactly that and serves the dataset-backed mock. Parsers
that default instead of raising leave that fallback dead and the wrong answer live.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import utcnow
from app.nac.nokia import (
    NokiaResponseError,
    parse_congestion,
    parse_connectivity_status,
    parse_location,
    parse_reachability_status,
    parse_roaming,
)


# ── Reachability v1 ─────────────────────────────────────────────────────────

def test_reachable_true_with_data_bearer():
    assert parse_reachability_status({"reachable": True, "connectivity": ["SMS", "DATA"]}) == "CONNECTED_DATA"


def test_reachable_true_without_bearer_list_is_still_connected():
    # Absent bearers refine nothing about a device the operator already called
    # reachable; SMS-only is the conservative read, and it is still "connected".
    assert parse_reachability_status({"reachable": True}) == "CONNECTED_SMS"


def test_reachable_false_is_the_only_route_to_not_connected():
    assert parse_reachability_status({"reachable": False}) == "NOT_CONNECTED"


@pytest.mark.parametrize(
    "body",
    [
        {},                                  # field absent entirely
        {"reachable": None},                 # explicit null
        {"reachable": "false"},              # string, as some gateways serialise it
        {"status": "REACHABLE"},             # a different response shape altogether
        {"reachable": 0},                    # numeric, falsy — the old code's worst case
    ],
)
def test_missing_or_non_boolean_reachable_raises(body):
    # Every one of these used to read as NOT_CONNECTED: a confident "the device is
    # dark" derived from a body that never said so, which is the verdict that clears a
    # truck to drive into the desert.
    with pytest.raises(NokiaResponseError):
        parse_reachability_status(body)


def test_non_object_reachability_body_raises():
    with pytest.raises(NokiaResponseError):
        parse_reachability_status(["reachable"])


def test_connectivity_field_of_wrong_type_raises():
    with pytest.raises(NokiaResponseError):
        parse_reachability_status({"reachable": True, "connectivity": "DATA"})


# ── Connectivity v0 (the fallback endpoint) ─────────────────────────────────

def test_connectivity_v0_passes_through_stated_status():
    assert parse_connectivity_status({"connectivityStatus": "connected_data"}) == "CONNECTED_DATA"


def test_unknown_is_preserved_and_is_not_not_connected():
    # UNKNOWN is a claim the operator makes: "we cannot tell you". NOT_CONNECTED is a
    # different claim: "we are sure this SIM is detached". Only the second is evidence
    # about a silent machine, so the adapter must not collapse one into the other.
    status = parse_connectivity_status({"connectivityStatus": "UNKNOWN"})
    assert status == "UNKNOWN"
    assert status != "NOT_CONNECTED"


@pytest.mark.parametrize(
    "body",
    [{}, {"connectivityStatus": None}, {"connectivityStatus": "DISCONNECTED"}, {"connectivityStatus": 3}],
)
def test_missing_or_unrecognised_connectivity_status_raises(body):
    # An unrecognised string is not UNKNOWN — it means we are reading something other
    # than the API this adapter was written against, and inventing UNKNOWN from it
    # hands the agent a status with nothing behind it.
    with pytest.raises(NokiaResponseError):
        parse_connectivity_status(body)


# ── Roaming v0 ──────────────────────────────────────────────────────────────

def test_country_name_as_list_is_read_whole():
    assert parse_roaming({"roaming": True, "countryName": ["HU"]}) == (True, "HU")


def test_country_name_as_bare_string_is_not_indexed_into():
    # The bug this exists for: names[0] on "HU" yields "H", which is not a country,
    # and "H" != "SA" closed the incident as roaming-out — no ML, no location lookup,
    # no work order, for a machine that may genuinely be broken.
    roaming, country = parse_roaming({"roaming": True, "countryName": "HU"})
    assert (roaming, country) == (True, "HU")


def test_three_letter_and_lowercase_country_codes_normalise():
    assert parse_roaming({"roaming": True, "countryName": ["sau"]}) == (True, "SAU")


def test_absent_country_is_not_an_error():
    # Operators omit the country when the device is home. Absent is not malformed.
    assert parse_roaming({"roaming": False}) == (False, None)
    assert parse_roaming({"roaming": False, "countryName": []}) == (False, None)


@pytest.mark.parametrize(
    "body",
    [
        {"countryName": ["HU"]},                    # roaming flag missing
        {"roaming": "true", "countryName": ["HU"]},  # flag as a string
        {"roaming": True, "countryName": [36]},      # numeric country code
        {"roaming": True, "countryName": ["Hungary"]},  # a name, not a code
    ],
)
def test_unreadable_roaming_body_raises(body):
    with pytest.raises(NokiaResponseError):
        parse_roaming(body)


# ── Congestion Insights v0 ──────────────────────────────────────────────────

def _window(level: str, conf, start: datetime) -> dict:
    return {
        "congestionLevel": level,
        "confidenceLevel": conf,
        "startsAt": start.isoformat().replace("+00:00", "Z"),
    }


def test_single_window_is_read_as_a_pair():
    now = utcnow()
    assert parse_congestion({"congestionInsights": [_window("high", 80, now)]}) == ("High", 80)


def test_bare_list_response_is_accepted():
    assert parse_congestion([_window("LOW", 70, utcnow())]) == ("Low", 70)


def test_window_is_chosen_by_timestamp_not_position():
    # The old code took entries[0] on an assumption about ordering that the sandbox
    # never documented. Here the current window is deliberately last in the list.
    now = utcnow()
    stale = _window("High", 90, now - timedelta(hours=6))
    current = _window("Low", 85, now - timedelta(minutes=2))
    assert parse_congestion({"congestionInsights": [stale, current]}) == ("Low", 85)
    # Same two windows, opposite order — same answer. That is the whole property.
    assert parse_congestion({"congestionInsights": [current, stale]}) == ("Low", 85)


def test_future_only_windows_pick_the_nearest_one_deterministically():
    now = utcnow()
    far = _window("High", 90, now + timedelta(hours=4))
    near = _window("Low", 60, now + timedelta(minutes=30))
    assert parse_congestion([far, near]) == ("Low", 60)
    assert parse_congestion([near, far]) == ("Low", 60)


def test_naive_timestamps_do_not_explode_the_comparison():
    # fromisoformat returns a naive datetime for a string with no offset, and comparing
    # it against the timezone-aware "now" raises TypeError. Operator times are UTC.
    now = utcnow()
    naive = {"congestionLevel": "High", "confidenceLevel": 75,
             "startsAt": (now - timedelta(minutes=5)).replace(tzinfo=None).isoformat()}
    aware = _window("Low", 80, now - timedelta(hours=3))
    assert parse_congestion([aware, naive]) == ("High", 75)


def test_missing_confidence_is_refused_rather_than_bypassing_the_floor():
    # assess_silence only applies MIN_CONGESTION_CONFIDENCE when the confidence is a
    # number, so a level arriving with confidence=None counted as full-strength
    # evidence and could hold back a dispatch on its own. Both halves or neither.
    with pytest.raises(NokiaResponseError):
        parse_congestion([{"congestionLevel": "High", "startsAt": utcnow().isoformat()}])
    with pytest.raises(NokiaResponseError):
        parse_congestion([{"congestionLevel": "High", "confidenceLevel": None,
                           "startsAt": utcnow().isoformat()}])


def test_observed_sandbox_congestion_payload():
    """The literal body the Nokia sandbox returned on 2026-09-04.

    A bare array of five-minute windows keyed on timeIntervalStart. The two windows
    disagree on confidence — 95 and 58, either side of the agent's floor — so reading
    the wrong one changes whether the reading counts as evidence at all.
    """
    observed = [
        {"timeIntervalStart": "2026-09-04T15:17:13.870642Z",
         "timeIntervalStop": "2026-09-04T15:22:13.870642Z",
         "congestionLevel": "Medium", "confidenceLevel": 95},
        {"timeIntervalStart": "2026-09-04T15:12:13.870642Z",
         "timeIntervalStop": "2026-09-04T15:17:13.870642Z",
         "congestionLevel": "Medium", "confidenceLevel": 58},
    ]
    assert parse_congestion(observed) == ("Medium", 95)
    assert parse_congestion(list(reversed(observed))) == ("Medium", 95)


def test_observed_sandbox_bodies_still_parse():
    # The other three verified 2026-09-04 responses, so a parser tightened against
    # malformed shapes cannot start rejecting the real ones.
    assert parse_reachability_status(
        {"device": {"phoneNumber": "+99999991000"}, "reachable": True,
         "connectivity": ["SMS"], "lastStatusTime": "2026-09-04T15:22:13.348436Z"}
    ) == "CONNECTED_SMS"
    assert parse_roaming(
        {"lastStatusTime": "2026-09-04T15:22:13.616871Z", "roaming": True,
         "countryCode": 36, "countryName": ["HU"]}
    ) == (True, "HU")
    lat, lon, accuracy, _ = parse_location(
        {"lastLocationTime": "2026-09-04T15:22:14.120242Z",
         "area": {"areaType": "CIRCLE",
                  "center": {"latitude": 47.48627616952785, "longitude": 19.07915612501993},
                  "radius": 1000}}
    )
    assert (round(lat, 4), round(lon, 4), accuracy) == (47.4863, 19.0792, 1000.0)


@pytest.mark.parametrize("conf", ["80", 101, -1, True])
def test_non_numeric_or_out_of_range_confidence_raises(conf):
    with pytest.raises(NokiaResponseError):
        parse_congestion([_window("High", conf, utcnow())])


@pytest.mark.parametrize(
    "body",
    [
        {},                                                        # no windows key
        {"congestionInsights": []},                                # empty list
        [{"congestionLevel": "SEVERE", "confidenceLevel": 80}],    # level off-enum
        [{"confidenceLevel": 80, "startsAt": "2026-09-01T00:00:00Z"}],  # no level
        ["High"],                                                  # windows aren't objects
    ],
)
def test_unreadable_congestion_body_raises(body):
    with pytest.raises(NokiaResponseError):
        parse_congestion(body)


def test_several_undated_windows_cannot_be_ranked():
    # With more than one window and no timestamps there is no defensible way to pick;
    # taking the first is exactly the undocumented assumption this replaced.
    with pytest.raises(NokiaResponseError):
        parse_congestion([
            {"congestionLevel": "High", "confidenceLevel": 80},
            {"congestionLevel": "Low", "confidenceLevel": 80},
        ])


# ── Location Retrieval v0 ───────────────────────────────────────────────────

def _area(lat, lon, radius=1200, when="2026-09-01T10:00:00Z") -> dict:
    return {
        "lastLocationTime": when,
        "area": {"areaType": "CIRCLE", "center": {"latitude": lat, "longitude": lon},
                 "radius": radius},
    }


def test_well_formed_location_parses():
    lat, lon, accuracy, as_of = parse_location(_area(27.5581, 34.9196))
    assert (lat, lon, accuracy) == (27.5581, 34.9196, 1200.0)
    assert as_of == datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def test_absent_radius_falls_back_to_the_sandbox_default_circle():
    _, _, accuracy, _ = parse_location(_area(27.5, 34.9, radius=None))
    assert accuracy == 1000.0


def test_absent_timestamp_is_allowed():
    _, _, _, as_of = parse_location(_area(27.5, 34.9, when=None))
    assert as_of.tzinfo is not None


def test_naive_location_timestamp_comes_back_timezone_aware():
    # A naive as_of would raise TypeError against utcnow() somewhere far from here.
    _, _, _, as_of = parse_location(_area(27.5, 34.9, when="2026-09-01T10:00:00"))
    assert as_of.tzinfo is not None
    assert as_of < utcnow() + timedelta(days=1)


@pytest.mark.parametrize(
    "body",
    [
        {},                                                       # no area
        {"area": {}},                                             # no centre
        {"area": {"center": {}}},                                 # no coordinates
        {"area": {"center": {"latitude": 27.5}}},                 # longitude missing
        {"area": {"center": {"latitude": "27.5", "longitude": "34.9"}}},  # strings
        {"area": {"center": {"latitude": 127.5, "longitude": 34.9}}},     # off the globe
        {"area": {"center": {"latitude": None, "longitude": None}}},
    ],
)
def test_malformed_location_raises_instead_of_returning_null_island(body):
    with pytest.raises(NokiaResponseError):
        parse_location(body)


def test_exact_zero_zero_is_treated_as_a_defaulted_response():
    # Not a coordinate this platform will ever legitimately receive: it is open ocean
    # in the Gulf of Guinea, thousands of kilometres from any site. Reaching the mock
    # beats routing a technician there.
    with pytest.raises(NokiaResponseError):
        parse_location(_area(0.0, 0.0))


def test_unreadable_location_timestamp_raises():
    # Absent is fine; present-but-unreadable is not. Substituting "now" would age a
    # stale fix to zero seconds old, which is precisely what maxAge=60 asked about.
    with pytest.raises(NokiaResponseError):
        parse_location(_area(27.5, 34.9, when="last tuesday"))


def test_non_positive_radius_raises():
    with pytest.raises(NokiaResponseError):
        parse_location(_area(27.5, 34.9, radius=0))


# ── The fallback these raises exist to arm ──────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_live_response_reaches_the_mock():
    """End to end for the actual point: a raise here becomes a mock answer there.

    Without an exception the FallbackNaCClient wrapper is unreachable code — it catches
    and nothing ever throws — and a malformed body is served to the agent as fact.
    """
    from app.nac.base import Reachability
    from app.nac.factory import FallbackNaCClient

    class BrokenLive:
        async def get_reachability(self, asset_id: str) -> Reachability:
            # Exactly what the client now does with a body missing 'reachable'.
            parse_reachability_status({"connectivity": ["SMS"]})
            raise AssertionError("unreachable")

        async def get_location(self, asset_id: str):
            parse_location({"area": {"center": {}}})
            raise AssertionError("unreachable")

    class StubMock:
        async def get_reachability(self, asset_id: str) -> Reachability:
            return Reachability(asset_id=asset_id, status="CONNECTED_DATA",
                                as_of=utcnow(), source="mock")

        async def get_location(self, asset_id: str):
            from app.nac.base import DeviceLocation
            return DeviceLocation(asset_id=asset_id, latitude=27.5, longitude=34.9,
                                  accuracy_m=30.0, as_of=utcnow(), source="mock")

    client = FallbackNaCClient(BrokenLive(), StubMock())
    reach = await client.get_reachability("EQ-0001")
    assert reach.source == "mock" and client.last_source == "mock"
    loc = await client.get_location("EQ-0001")
    assert loc.source == "mock" and (loc.latitude, loc.longitude) != (0.0, 0.0)
