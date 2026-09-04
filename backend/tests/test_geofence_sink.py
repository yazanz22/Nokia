"""The callback sink is configuration, not something the caller can write.

Registering a CAMARA geofencing subscription means handing the operator a URL it
will POST to, on our Nokia credentials. The live-check endpoint that registers it is
open on a public deploy, so if the sink were derived from the request — as it was,
via ``request.base_url`` — the Host header would decide where the operator sends
traffic. Anyone able to reach the demo could point a real subscription made on our
account at a server of their choosing.

So these tests spoof the Host header and assert it never reaches the operator, in
both directions: with a public URL configured (the configured one wins) and without
(nothing is registered at all, rather than a quiet fall back to the header).

Note the app is built directly rather than through the lifespan context manager:
``TestClient(app)`` without ``with`` skips startup, so the simulator and the anomaly
detector stay stopped and these tests exercise one request each, not a running demo.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.models import utcnow
from app.nac.base import DeviceLocation, Reachability
from app.ratelimit import live_check_limiter
from app.routes import debug as debug_routes

ATTACKER_HOST = "evil.attacker.example"
GOOD_BASE = "https://sentinel.example.test"
SINK_PATH = "/api/nac/geofence-callback"


class FakeLiveClient:
    """Stands in for the Nokia sandbox and records what it was asked to register."""

    def __init__(self) -> None:
        self.existing: list = []
        self.sinks: list[str] = []

    async def get_reachability(self, asset_id: str) -> Reachability:
        return Reachability(
            asset_id=asset_id,
            status="CONNECTED_DATA",
            congestion_level="Low",
            congestion_confidence=90,
            as_of=utcnow(),
            source="live",
        )

    async def get_location(self, asset_id: str) -> DeviceLocation:
        return DeviceLocation(
            asset_id=asset_id,
            latitude=28.0,
            longitude=35.0,
            accuracy_m=1000.0,
            as_of=utcnow(),
            source="live",
        )

    async def _post_list_subscriptions(self) -> list:
        return self.existing

    async def create_geofence_subscription(self, sink: str) -> dict:
        self.sinks.append(sink)
        return {"id": "sub-123"}


@pytest.fixture
def fake_live(monkeypatch):
    """A live CAMARA client that never leaves the process.

    Without NAC_API_KEY the endpoint is a 503, and with one it would spend real
    sandbox quota — neither belongs in a test.
    """
    client = FakeLiveClient()
    monkeypatch.setattr(debug_routes, "get_live_client", lambda: client)
    # The per-client limiter is process-wide and keyed on the caller, so requests from
    # one test would otherwise accumulate against the next.
    live_check_limiter._hits.clear()
    return client


@pytest.fixture
def public_base(monkeypatch):
    """Set PUBLIC_BASE_URL for the duration of one test. Defaults to unset."""
    settings = get_settings()
    monkeypatch.setattr(settings, "public_base_url", "")
    return lambda value: monkeypatch.setattr(settings, "public_base_url", value)


def _live_check(host: str = ATTACKER_HOST) -> dict:
    client = TestClient(app)
    response = client.post("/api/nac/live-check", headers={"Host": host})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_spoofed_host_actually_reaches_request_base_url(fake_live, public_base):
    """Guards the rest of this file.

    If the test client quietly rewrote Host, or Starlette ignored it, every assertion
    below would pass against the vulnerable code too. So observe the server-side
    Request the handler is given and confirm ``request.base_url`` — the expression the
    sink used to be built from — really does carry the attacker's host.
    """
    seen: list = []
    monkeypatch_target = debug_routes.live_check_limiter
    original = monkeypatch_target.check

    def _capture(request):
        seen.append(str(request.base_url))
        return original(request)

    monkeypatch_target.check = _capture  # type: ignore[method-assign]
    try:
        public_base(GOOD_BASE)
        _live_check(host=ATTACKER_HOST)
    finally:
        monkeypatch_target.check = original  # type: ignore[method-assign]

    assert seen and ATTACKER_HOST in seen[0]


def test_configured_base_url_wins_over_the_host_header(fake_live, public_base):
    public_base(GOOD_BASE)
    body = _live_check(host=ATTACKER_HOST)

    assert fake_live.sinks == [f"{GOOD_BASE}{SINK_PATH}"]
    assert body["geofencing"]["status"] == "created"
    assert body["geofencing"]["sink"] == f"{GOOD_BASE}{SINK_PATH}"
    # Nothing anywhere in the response echoes the attacker's host either.
    assert ATTACKER_HOST not in json.dumps(body)


def test_without_a_public_base_url_nothing_is_registered(fake_live, public_base):
    """The honest answer, not a fall back to the Host header."""
    body = _live_check(host=ATTACKER_HOST)

    assert fake_live.sinks == []
    geo = body["geofencing"]
    assert geo["status"] == "needs public url"
    assert "sink" not in geo
    # And it says why, rather than leaving the panel to imply the operator refused.
    assert "PUBLIC_BASE_URL" in geo["detail"]
    assert ATTACKER_HOST not in json.dumps(body)


@pytest.mark.parametrize(
    "value",
    [
        "sentinel.example.test",  # no scheme — would be sent as a relative sink
        "//sentinel.example.test",  # protocol-relative
        "/api",  # path only
        "javascript:alert(1)",
        "ftp://sentinel.example.test",
        "https://",  # scheme, no host
        "   ",
        "https://sentinel.example.test\nX-Evil: 1",  # header injection into the sink
    ],
)
def test_a_base_url_that_is_not_absolute_http_is_refused(value, fake_live, public_base):
    """Whatever we build gets sent to an operator, so it is validated before it goes."""
    public_base(value)
    assert get_settings().public_url(SINK_PATH) is None

    body = _live_check(host=ATTACKER_HOST)
    assert fake_live.sinks == []
    assert body["geofencing"]["status"] == "needs public url"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("https://a.example", f"https://a.example{SINK_PATH}"),
        ("https://a.example/", f"https://a.example{SINK_PATH}"),
        ("  https://a.example/  ", f"https://a.example{SINK_PATH}"),
        ("http://localhost:8000", f"http://localhost:8000{SINK_PATH}"),
        ("https://a.example/filo", f"https://a.example/filo{SINK_PATH}"),
    ],
)
def test_accepted_base_urls_build_the_expected_sink(configured, expected):
    assert Settings(public_base_url=configured).public_url(SINK_PATH) == expected


def test_an_existing_subscription_is_reused_and_never_builds_a_sink(fake_live, public_base):
    """The path that must not create one either — a proof panel should not accumulate
    subscriptions in someone's operator account."""
    public_base(GOOD_BASE)
    fake_live.existing = [{"id": "sub-existing"}]

    body = _live_check(host=ATTACKER_HOST)
    assert fake_live.sinks == []
    assert body["geofencing"]["status"] == "existing"
    assert body["geofencing"]["subscription_id"] == "sub-existing"


def test_health_truncates_the_provider_error(monkeypatch):
    """A provider exception can carry the request URL and fragments of the body, and
    this endpoint is open on a public deploy."""
    import app.agent as agent_mod

    monkeypatch.setattr(agent_mod, "last_agent_error", "APIError: " + "x" * 5000)
    body = TestClient(app).get("/api/debug/health").json()

    assert len(body["last_agent_error"]) == 160
    assert body["last_agent_error"].startswith("APIError: ")

    monkeypatch.setattr(agent_mod, "last_agent_error", None)
    assert TestClient(app).get("/api/debug/health").json()["last_agent_error"] is None


# ── Congestion Insights reporting ────────────────────────────────────────────
# The live panel used to render its congestion block only when a level came back, so a
# swallowed best-effort call made the whole thing vanish with nothing on screen — while
# the demo script sends the presenter to it for "real level, real confidence". This is
# also the family that makes the coverage verdict reachable against a real operator at
# all, since the live client leaves signal strength and neighbour failures None. The
# panel now needs to tell "asked and got nothing" apart from "asked and got a reading",
# so the endpoint has to say which happened.


class _QuietLiveClient(FakeLiveClient):
    """A sandbox whose congestion query gave nothing usable."""

    async def get_reachability(self, asset_id: str) -> Reachability:
        return Reachability(
            asset_id=asset_id,
            status="CONNECTED_DATA",
            congestion_level=None,
            congestion_confidence=None,
            as_of=utcnow(),
            source="live",
        )


def test_a_congestion_reading_is_reported_as_returned(fake_live, public_base):
    body = _live_check()
    block = body["congestion_insights"]

    assert block["attempted"] is True
    assert block["returned"] is True
    assert block["result"]["congestion_level"] == "Low"
    assert block["result"]["confidence_level"] == 90
    # The floor comes from the backend that applies it. The frontend used to hardcode
    # its own copy of 50, which is exactly how two thresholds drift apart.
    from app.agent.tools import MIN_CONGESTION_CONFIDENCE

    assert block["min_confidence"] == MIN_CONGESTION_CONFIDENCE


def test_a_silent_congestion_query_is_reported_not_omitted(monkeypatch, public_base):
    import app.routes.debug as debug_routes

    monkeypatch.setattr(debug_routes, "get_live_client", lambda: _QuietLiveClient())
    block = _live_check()["congestion_insights"]

    # The call still went out — it rides inside the reachability step — so the panel
    # must be able to say so rather than showing the presenter an empty space.
    assert block["attempted"] is True
    assert block["returned"] is False
    assert block["note"]
    # And the shape the panel already consumed is unchanged.
    assert block["result"]["congestion_level"] is None
    assert block["result"]["confidence_level"] is None
