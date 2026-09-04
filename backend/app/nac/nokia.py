"""Live Nokia Network as Code adapter — real CAMARA calls.

All SDK/transport specifics are isolated here; the rest of the codebase depends only
on the :class:`NetworkClient` protocol in ``base.py``.

Verified against the Nokia sandbox on 2026-09-01:

    POST /device-status/device-reachability-status/v1/retrieve  {"device":{...}}
        -> {"reachable": true, "connectivity": ["SMS"], "lastStatusTime": "..."}

    POST /device-status/v0/roaming        {"device":{"phoneNumber":"+999..."}}
        -> {"roaming": true, "countryCode": 36, "countryName": ["HU"], ...}

    POST /location-retrieval/v0/retrieve  {"device":{...}, "maxAge": 60}
        -> {"lastLocationTime": "...", "area": {"areaType":"CIRCLE",
            "center": {"latitude": .., "longitude": ..}, "radius": 1000}}

    POST /congestion-insights/v0/query    {"device":{...}}   (re-verified 2026-09-04)
        -> [{"timeIntervalStart": "...", "timeIntervalStop": "...",
             "congestionLevel": "Medium", "confidenceLevel": 95}, ...]
        A bare JSON array of five-minute windows. Nothing documents the order, and the
        confidence differs per window (95 and 58 in the observed pair — either side of
        the floor the agent applies), so which window is read is a real decision.

Reachability Status v1 is the primary call — it is the CAMARA API the solution is
built around, and its ``reachable`` flag maps directly onto the same field in our
telemetry. ``/device-status/v0/connectivity`` is kept as a fallback.

We call these directly with httpx rather than through the generated
``network-as-code`` SDK: the SDK defaults to a different base host, and the request
shape here is three small POSTs. Fewer moving parts to fail on stage.

Auth is RapidAPI-style: ``x-rapidapi-key`` plus ``x-rapidapi-host``.

Response parsing lives in the module-level ``parse_*`` functions rather than inside the
client, so every failure mode can be exercised against a literal payload with no network
in the way (``tests/test_nokia_parsing.py``). They raise :class:`NokiaResponseError` on
anything they cannot read: this adapter's job is to report what the operator actually
said, and where it cannot, to fail loudly enough that ``FallbackNaCClient`` serves the
mock instead. Defaulting is what produced confident nonsense — a dark device, a
technician routed to Null Island, an unconfident congestion reading counted as proof.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..config import get_settings
from ..models import utcnow
from .base import DeviceLocation, ReachStatus, Reachability, _now

log = logging.getLogger("nac.live")

# Statuses the operator may *state*. UNKNOWN is one of them and is not the same claim
# as NOT_CONNECTED: "the network cannot tell you" versus "the network is sure this SIM
# is detached". Only the second one is evidence about a silent machine. Anything the
# operator did not state is not in here — it raises instead of being rounded down to
# the nearest plausible answer.
_CONNECTIVITY_STATUSES = {"CONNECTED_DATA", "CONNECTED_SMS", "NOT_CONNECTED", "UNKNOWN"}
_CONGESTION_LEVELS = {"None", "Low", "Medium", "High"}

REACHABILITY_PATH = "/device-status/device-reachability-status/v1/retrieve"
CONNECTIVITY_PATH = "/device-status/v0/connectivity"  # fallback
ROAMING_PATH = "/device-status/v0/roaming"
LOCATION_PATH = "/location-retrieval/v0/retrieve"
# Congestion Insights grades the serving area. Device Status exposes no radio
# metrics, so this is the only network-side evidence that a silence is the
# network's doing rather than the machine's.
CONGESTION_PATH = "/congestion-insights/v0/query"
GEOFENCE_PATH = "/geofencing-subscriptions/v0.3/subscriptions"


class NokiaResponseError(ValueError):
    """The sandbox answered, but not with a body we can honestly read.

    Every parser below raises this instead of substituting a default, because the
    defaults were all *confident wrong answers*: a missing ``reachable`` used to read as
    "the network is sure this machine is detached", and a missing ``latitude`` used to
    read as 0.0 — Null Island, in the Gulf of Guinea, roughly 4,000 km from the nearest
    thing we would ever dispatch a technician to.

    Raising is the point. ``FallbackNaCClient`` wraps every live call in a
    ``try/except`` whose whole job is to serve the dataset-backed mock when the sandbox
    cannot answer, and a parser that never raises is a parser that keeps that mechanism
    permanently dead. A body we cannot read *is* the sandbox failing to answer.
    """


def _mapping(body: object, what: str) -> dict:
    if not isinstance(body, dict):
        raise NokiaResponseError(f"{what}: expected a JSON object, got {type(body).__name__}")
    return body


def _timestamp(raw: object, field: str) -> datetime:
    """Parse a CAMARA timestamp into something it is safe to *compare*.

    ``fromisoformat`` happily returns a naive datetime for a string with no offset, and
    a naive datetime raises TypeError the moment it meets the timezone-aware ones the
    rest of the app makes with ``utcnow()`` — far away from here, in whatever code did
    the comparison. Operator timestamps are UTC, so stamp the timezone on rather than
    letting a booby-trapped datetime out of this module.
    """
    if not isinstance(raw, str):
        raise NokiaResponseError(f"{field}: expected an ISO-8601 string, got {type(raw).__name__}")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NokiaResponseError(f"{field}: not an ISO-8601 timestamp ({raw!r})") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_reachability_status(body: object) -> ReachStatus:
    """Read ``/device-reachability-status/v1/retrieve``.

    ``reachable`` must be a genuine boolean the operator sent. Reading a missing field
    as False turned every malformed body into "the device is dark", which is the exact
    verdict that authorises a truck into the desert.
    """
    data = _mapping(body, "reachability v1")
    reachable = data.get("reachable")
    if not isinstance(reachable, bool):
        raise NokiaResponseError(
            "reachability v1: 'reachable' missing or not a boolean "
            f"(got {reachable!r}) — refusing to read that as 'device is dark'"
        )
    if not reachable:
        return "NOT_CONNECTED"

    # Which bearers are up only refines a device we already know is attached, so an
    # absent list is not fatal — SMS-only is the conservative read of "reachable".
    modes = data.get("connectivity")
    if modes is None:
        return "CONNECTED_SMS"
    if not isinstance(modes, (list, tuple)):
        raise NokiaResponseError(f"reachability v1: 'connectivity' is not a list ({modes!r})")
    return "CONNECTED_DATA" if "DATA" in {str(m).upper() for m in modes} else "CONNECTED_SMS"


def parse_connectivity_status(body: object) -> ReachStatus:
    """Read the ``/device-status/v0/connectivity`` fallback.

    A status string we do not recognise is not UNKNOWN — UNKNOWN is a claim the
    operator makes on purpose. An unrecognised string means we are talking to something
    other than what this adapter was written against, and guessing at it produces a
    verdict with nothing behind it.
    """
    data = _mapping(body, "connectivity v0")
    raw = data.get("connectivityStatus")
    if not isinstance(raw, str):
        raise NokiaResponseError(
            f"connectivity v0: 'connectivityStatus' missing or not a string (got {raw!r})"
        )
    status = raw.strip().upper()
    if status not in _CONNECTIVITY_STATUSES:
        raise NokiaResponseError(f"connectivity v0: unrecognised connectivityStatus {raw!r}")
    return status  # type: ignore[return-value]


def parse_roaming(body: object) -> tuple[bool, str | None]:
    """Read ``/device-status/v0/roaming`` into (roaming, ISO country code).

    ``countryName`` arrives from the sandbox as ``["HU"]`` but the CAMARA schema also
    permits a bare string, and the old ``names[0]`` indexed straight into it: ``"HU"``
    became ``"H"``, a country code that exists nowhere, which then compared unequal to
    HOME_COUNTRY and closed the incident as "roaming onto a foreign network" — no ML,
    no location lookup, no work order, for a machine that might well be broken.
    """
    data = _mapping(body, "roaming v0")
    roaming = data.get("roaming")
    if not isinstance(roaming, bool):
        raise NokiaResponseError(f"roaming v0: 'roaming' missing or not a boolean (got {roaming!r})")

    raw = data.get("countryName")
    if raw is None or raw == []:
        # Operators omit the country when the device is home. Absent is not malformed.
        return roaming, None
    name = raw[0] if isinstance(raw, (list, tuple)) else raw
    if not isinstance(name, str) or not (2 <= len(name.strip()) <= 3) or not name.strip().isalpha():
        raise NokiaResponseError(
            f"roaming v0: 'countryName' is not an ISO country code ({raw!r})"
        )
    return roaming, name.strip().upper()


def _congestion_start(entry: dict) -> datetime | None:
    # timeIntervalStart is what the sandbox actually sends; the rest are the spellings
    # the CAMARA drafts use, accepted so a schema revision does not silently blind this.
    for field in ("timeIntervalStart", "startsAt", "startTime", "start", "from"):
        raw = entry.get(field)
        if raw is not None:
            return _timestamp(raw, f"congestion '{field}'")
    return None


def parse_congestion(body: object) -> tuple[str, int]:
    """Read ``/congestion-insights/v0/query`` into (level, confidence).

    Both halves or neither. A level with no ``confidenceLevel`` used to sail past the
    MIN_CONGESTION_CONFIDENCE floor in ``assess_silence`` entirely — that check only
    fires when the confidence is a number — so an operator reading with no stated
    confidence counted as full-strength evidence and could hold back a dispatch on its
    own. A reading nobody vouched for is not evidence, so it is refused here rather
    than laundered into one downstream.
    """
    if isinstance(body, list):
        entries = body
    else:
        data = _mapping(body, "congestion v0")
        entries = data.get("congestionInsights") or []
    if not isinstance(entries, list) or not entries:
        raise NokiaResponseError("congestion v0: no congestion windows in the response")
    windows = [e for e in entries if isinstance(e, dict)]
    if not windows:
        raise NokiaResponseError("congestion v0: congestion windows are not objects")

    # Which window is "now" is picked by its own timestamp, never by its position. The
    # sandbox response ordering was never documented anywhere — the old code took
    # entries[0] on the assumption that the list came back most-recent-first, and
    # nothing in Nokia's docs or the observed responses ever confirmed that. A reversed
    # list would have graded the silence against a window from hours ago.
    dated = [(start, e) for e in windows if (start := _congestion_start(e)) is not None]
    if len(windows) == 1:
        current = windows[0]
    elif not dated:
        raise NokiaResponseError(
            "congestion v0: several windows and none carries a timestamp — "
            "cannot tell which one covers now"
        )
    else:
        now = utcnow()
        started = [pair for pair in dated if pair[0] <= now]
        current = (max(started, key=lambda p: p[0]) if started else min(dated, key=lambda p: p[0]))[1]

    raw_level = current.get("congestionLevel")
    if not isinstance(raw_level, str):
        raise NokiaResponseError(f"congestion v0: 'congestionLevel' missing or not a string ({raw_level!r})")
    level = raw_level.strip().capitalize()
    if level not in _CONGESTION_LEVELS:
        raise NokiaResponseError(f"congestion v0: unrecognised congestionLevel {raw_level!r}")

    conf = current.get("confidenceLevel")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        raise NokiaResponseError(
            f"congestion v0: 'confidenceLevel' missing or not a number (got {conf!r}) — "
            "a reading with no stated confidence is not evidence"
        )
    if not 0 <= conf <= 100:
        raise NokiaResponseError(f"congestion v0: confidenceLevel out of range ({conf!r})")
    return level, int(conf)


def parse_location(body: object) -> tuple[float, float, float, datetime]:
    """Read ``/location-retrieval/v0/retrieve`` into (lat, lon, accuracy_m, as_of).

    The old defaults turned any shape we did not expect into (0.0, 0.0) with 1 km
    accuracy — a work order routing a technician to Null Island, and one that looks
    exactly as authoritative on the dashboard as a real fix.
    """
    data = _mapping(body, "location v0")
    area = data.get("area")
    if not isinstance(area, dict):
        raise NokiaResponseError(f"location v0: 'area' missing or not an object ({area!r})")
    center = area.get("center")
    if not isinstance(center, dict):
        raise NokiaResponseError(f"location v0: 'area.center' missing or not an object ({center!r})")

    coords: list[float] = []
    for field, limit in (("latitude", 90.0), ("longitude", 180.0)):
        value = center.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise NokiaResponseError(
                f"location v0: '{field}' missing or not a number (got {value!r})"
            )
        if not -limit <= value <= limit:
            raise NokiaResponseError(f"location v0: '{field}' out of range ({value!r})")
        coords.append(float(value))
    lat, lon = coords
    # Exactly (0, 0) is the signature of a defaulted response rather than a fix: it is
    # open ocean, and no device this platform will ever ask about is there. Treated as
    # a malformed answer so it reaches the fallback instead of a dispatch queue.
    if lat == 0.0 and lon == 0.0:
        raise NokiaResponseError("location v0: centre is exactly (0, 0) — Null Island, not a fix")

    radius = area.get("radius")
    if radius is None:
        accuracy = 1000.0  # the sandbox's own default circle when it omits one
    elif isinstance(radius, bool) or not isinstance(radius, (int, float)) or radius <= 0:
        raise NokiaResponseError(f"location v0: 'radius' is not a positive number ({radius!r})")
    else:
        accuracy = float(radius)

    raw_time = data.get("lastLocationTime")
    # Absent is allowed — the operator said nothing about age. Present-but-unreadable is
    # not: silently substituting "now" would age a stale fix to zero seconds old, which
    # is the one thing maxAge=60 was asked for.
    as_of = utcnow() if raw_time is None else _timestamp(raw_time, "location 'lastLocationTime'")
    return lat, lon, accuracy, as_of


class NokiaNaCClient:
    """CAMARA Device Status + Location Retrieval against the Nokia sandbox."""

    source = "live"

    def __init__(self) -> None:
        settings = get_settings()
        self._device_map = settings.device_map()
        self._default_device = settings.nac_default_device.strip()
        self._client = httpx.AsyncClient(
            base_url=f"https://{settings.nac_api_host}",
            headers={
                "x-rapidapi-key": settings.nac_api_key,
                "x-rapidapi-host": settings.nac_rapidapi_host,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(settings.nac_timeout_seconds),
        )

    def _device(self, asset_id: str) -> dict:
        """Map a fleet asset to a sandbox device.

        The sandbox issues a small pool of test MSISDNs, far fewer than our fleet, so
        assets without an explicit mapping fall back to NAC_DEFAULT_DEVICE. That keeps
        the calls genuinely live for any asset instead of failing for most of them.
        """
        phone = self._device_map.get(asset_id) or self._default_device
        if not phone:
            raise KeyError(
                f"no sandbox device for {asset_id}: set NAC_DEVICE_MAP or NAC_DEFAULT_DEVICE"
            )
        return {"phoneNumber": phone}

    async def _post(self, path: str, payload: dict) -> dict:
        resp = await self._client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_reachability(self, asset_id: str) -> Reachability:
        device = self._device(asset_id)
        try:
            # {"reachable": true, "connectivity": ["SMS"|"DATA"], ...}
            status = parse_reachability_status(await self._post(REACHABILITY_PATH, {"device": device}))
        except Exception as exc:  # noqa: BLE001
            log.warning("reachability v1 failed (%s) — trying connectivity v0", exc)
            # If v0 cannot answer either, the exception leaves this method on purpose:
            # there is no third source of truth here, and FallbackNaCClient serving the
            # mock is a better answer than a status we made up.
            status = parse_connectivity_status(await self._post(CONNECTIVITY_PATH, {"device": device}))

        # Roaming is a second, independent CAMARA signal: a device roaming out of
        # country is a coverage story, not a hardware story. Best-effort — never let
        # it fail the primary reachability answer.
        roaming = None
        country = None
        try:
            roaming, country = parse_roaming(await self._post(ROAMING_PATH, {"device": device}))
        except NokiaResponseError as exc:
            # A body we could not read is worth saying out loud: it means the roaming
            # branch of assess_silence is running blind on this call.
            log.warning("roaming response unreadable for %s: %s", asset_id, exc)
        except Exception as exc:  # noqa: BLE001
            log.debug("roaming lookup failed for %s: %s", asset_id, exc)

        # How degraded is the area serving this device? Best-effort, like roaming:
        # a missing answer must never take down the primary reachability result.
        # Reported as a pair or not at all — see parse_congestion on why a level
        # without a confidence must not reach the agent.
        congestion_level = None
        congestion_confidence = None
        try:
            congestion_level, congestion_confidence = parse_congestion(
                await self._post(CONGESTION_PATH, {"device": device})
            )
        except NokiaResponseError as exc:
            log.warning("congestion response unreadable for %s: %s", asset_id, exc)
        except Exception as exc:  # noqa: BLE001
            log.debug("congestion lookup failed for %s: %s", asset_id, exc)

        return Reachability(
            asset_id=asset_id,
            # Passed through exactly as the operator stated it, UNKNOWN included. Nothing
            # gets rounded to NOT_CONNECTED on the way out — the parsers raised rather
            # than hand us a status to coerce.
            status=status,
            # Device Status does not expose radio metrics; those come from the
            # telemetry side. Left as None so the agent knows they're unavailable
            # rather than reading a fabricated zero.
            signal_strength_dbm=None,
            neighbor_fail_count=None,
            roaming=roaming,
            country=country,
            congestion_level=congestion_level,
            congestion_confidence=congestion_confidence,
            as_of=_now(),
            source="live",
        )

    async def get_location(self, asset_id: str) -> DeviceLocation:
        device = self._device(asset_id)
        # A malformed body raises out of here rather than resolving to a coordinate.
        # This answer becomes a work order and a technician's route, so the fallback
        # serving a mock position is the only honest response to an unreadable one.
        lat, lon, accuracy, as_of = parse_location(
            await self._post(LOCATION_PATH, {"device": device, "maxAge": 60})
        )
        return DeviceLocation(
            asset_id=asset_id,
            latitude=lat,
            longitude=lon,
            accuracy_m=accuracy,
            as_of=as_of,
            source="live",
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post_list_subscriptions(self) -> list:
        """Existing perimeter watches. Named for symmetry with the POST below."""
        resp = await self._client.get(GEOFENCE_PATH)
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, list) else body.get("subscriptions", [])

    async def create_geofence_subscription(self, sink: str) -> dict:
        """Register a real boundary watch with the operator.

        Push, not poll: the network calls ``sink`` when the device leaves the area,
        which is what lets a fleet be watched without polling every machine. The
        fleet on the dashboard is simulated and its crossings are delivered by the
        mock, so this exists to show the subscription itself is real — the same
        pattern as every other call here.
        """
        from .base import SITE_CENTER, SITE_RADIUS_KM

        body = {
            "protocol": "HTTP",
            "sink": sink,
            "types": ["org.camaraproject.geofencing-subscriptions.v0.area-left"],
            "config": {
                "subscriptionDetail": {
                    "device": {"phoneNumber": self._default_device},
                    "area": {
                        "areaType": "CIRCLE",
                        "center": {
                            "latitude": SITE_CENTER[0],
                            "longitude": SITE_CENTER[1],
                        },
                        "radius": int(SITE_RADIUS_KM * 1000),
                    },
                },
                "initialEvent": False,
            },
        }
        return await self._post(GEOFENCE_PATH, body)
