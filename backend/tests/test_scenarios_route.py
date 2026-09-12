"""HTTP-level tests for the /api/scenarios routes.

These construct the FastAPI app directly. ``TestClient`` is deliberately not used as a
context manager: entering it runs the lifespan, which starts the simulator tick loop
and the anomaly detector, and this file is testing route contracts, not a live fleet.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ratelimit import inject_budget, inject_limiter, investigation_site_limiter
from app.routes.scenarios import reset_limiter
from app.simulator.engine import DRIFT_SCENARIO
from app.store import store


@pytest.fixture
def client():
    # The limiters and the budget are module-level singletons shared with the running
    # process, so a test that spends them would leak into the next one — and into the
    # count the demo has left. Hand every test a clean allowance and put it back.
    inject_limiter._hits.clear()
    investigation_site_limiter._hits.clear()
    reset_limiter._hits.clear()
    day, count = inject_budget._day, inject_budget._count
    inject_budget._day, inject_budget._count = "", 0
    yield TestClient(app)
    inject_limiter._hits.clear()
    investigation_site_limiter._hits.clear()
    reset_limiter._hits.clear()
    inject_budget._day, inject_budget._count = day, count


def test_one_ai_investigation_a_minute_site_wide(client):
    """Back-to-back investigations overrun the model's per-minute token quota, and the
    overrun silently finishes on the rule agent. The second one inside the minute must be
    refused instead, whoever sends it, while a perimeter drift (no agent) stays allowed
    and a refused click does not spend the minute."""
    eligible = client.get("/api/scenarios").json()["eligible_assets"]
    first, second, third = eligible[0], eligible[1], eligible[2]

    ok = client.post("/api/scenarios/inject", json={"asset_id": first, "scenario": "hardware"})
    assert ok.status_code == 200, ok.text

    # A 409 on the machine already under investigation is answered before the quota.
    again = client.post("/api/scenarios/inject", json={"asset_id": first, "scenario": "blindspot"})
    assert again.status_code == 409

    # A different visitor still shares the site's minute.
    blocked = client.post(
        "/api/scenarios/inject",
        json={"asset_id": second, "scenario": "blindspot"},
        headers={"x-forwarded-for": "203.0.113.9"},
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers

    drift = client.post("/api/scenarios/inject", json={"asset_id": third, "scenario": DRIFT_SCENARIO})
    assert drift.status_code == 200, drift.text


def test_advertised_eligibility_matches_what_inject_accepts(client):
    """Every asset the list endpoint offers must be one inject will actually take.

    The list used to advertise `anomaly` assets, which inject refuses with a 409 — so
    the dashboard could offer a target that was guaranteed to fail.
    """
    advertised = client.get("/api/scenarios").json()["eligible_assets"]
    assert advertised, "a freshly reset fleet should have injectable assets"

    # The advertised ones work.
    target = advertised[0]
    ok = client.post("/api/scenarios/inject", json={"asset_id": target, "scenario": "hardware"})
    assert ok.status_code == 200, ok.text
    assert store.assets[target].state == "anomaly"

    # And that same asset, now anomalous, has dropped off the advertised list rather
    # than being offered a second time and refused.
    again = client.get("/api/scenarios").json()["eligible_assets"]
    assert target not in again
    refused = client.post("/api/scenarios/inject", json={"asset_id": target, "scenario": "hardware"})
    assert refused.status_code == 409


def test_reset_is_rate_limited(client):
    """A curl loop against /scenarios/reset must not be able to hold the board blank."""
    limit = reset_limiter.limit
    for i in range(limit):
        r = client.post("/api/scenarios/reset")
        assert r.status_code == 200, f"reset {i} of the allowance was refused: {r.text}"

    blocked = client.post("/api/scenarios/reset")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers

    # The limit is per client, so the presenter's own machine keeps a full allowance
    # while someone else is being throttled.
    other = client.post("/api/scenarios/reset", headers={"x-forwarded-for": "203.0.113.7"})
    assert other.status_code == 200

    # Headroom check: nothing a rehearsal plausibly does can trip this. The documented
    # pre-demo call is one of these.
    assert limit >= 5
    assert client.post("/api/scenarios/reset?clear_memory=true", headers={"x-forwarded-for": "203.0.113.7"}).status_code == 200
