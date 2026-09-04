"""The predictive panel is polled every 30s per open tab and must not re-score for it.

Three things are being pinned here: the answer is memoised, the memo is keyed on the
in-service roster rather than on the process lifetime, and the fleet timestamp is the
instant the history was cut at rather than whatever the top-ranked row happens to say.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.config import get_settings
from app.ml.forecast import forecast_model
from app.routes import fleet
from app.store import store

pytestmark = pytest.mark.skipif(
    not forecast_model.available,
    reason="no forecast model / telemetry history — run ml/train.py",
)


@pytest.fixture(autouse=True)
def fresh_cache():
    """The module-level memo outlives store.reset(), so tests must clear it."""
    fleet._reset_cache()
    yield
    fleet._reset_cache()


@pytest.fixture
def score_calls(monkeypatch):
    """Count real scorings, so 'cached' means 'the model did not run again'."""
    calls: list[list[str]] = []
    original = forecast_model.score_fleet

    def counting(asset_ids):
        calls.append(list(asset_ids))
        return original(asset_ids)

    monkeypatch.setattr(forecast_model, "score_fleet", counting)
    return calls


async def test_second_call_is_served_from_the_cache(score_calls):
    first = await fleet.fleet_health()
    t0 = time.perf_counter()
    second = await fleet.fleet_health()
    elapsed = time.perf_counter() - t0

    assert len(score_calls) == 1, "the second poll re-scored the whole fleet"
    assert second is first
    assert elapsed < 0.05, f"cache hit took {elapsed * 1000:.0f}ms — it scored again"


async def test_dispatched_asset_leaves_the_panel(score_calls):
    before = await fleet.fleet_health()
    target = before["assets"][0]["asset_id"]

    # A technician is on the way: the machine is out of service, and a forecast about
    # it is no longer a prediction. A process-lifetime cache would keep showing it.
    store.set_asset_state(target, "dispatched")
    after = await fleet.fleet_health()

    assert len(score_calls) == 2, "the roster changed and the cache did not notice"
    assert after["fleet_size"] == before["fleet_size"] - 1
    assert target not in {row["asset_id"] for row in after["assets"]}
    assert target not in score_calls[1]


async def test_repaired_asset_comes_back(score_calls):
    before = await fleet.fleet_health()
    target = before["assets"][0]["asset_id"]
    store.set_asset_state(target, "dispatched")
    await fleet.fleet_health()

    # Work order completed — the machine reports again and belongs in the panel.
    store.set_asset_state(target, "healthy")
    back = await fleet.fleet_health()

    assert len(score_calls) == 3
    assert back["fleet_size"] == before["fleet_size"]
    assert target in {row["asset_id"] for row in back["assets"]}


async def test_healthy_to_anomaly_does_not_invalidate(score_calls):
    before = await fleet.fleet_health()
    target = before["assets"][0]["asset_id"]

    # Both states are in service and the history behind the score is identical, so
    # this must NOT cost a re-scoring — otherwise a twitchy fleet defeats the cache.
    store.set_asset_state(target, "anomaly")
    after = await fleet.fleet_health()

    assert len(score_calls) == 1
    assert after is before


async def test_as_of_is_the_cut_instant_not_the_top_row(monkeypatch):
    """The fleet timestamp must not move when the ranking does."""
    configured = get_settings().forecast_as_of
    assert configured, "this test needs FORECAST_AS_OF set"

    real = forecast_model.score_fleet(
        [aid for aid, a in store.assets.items() if a.state in ("healthy", "anomaly")]
    )
    stale = [row["as_of"] for row in real if row["as_of"] != configured]
    assert stale, "expected some assets whose history ends before the cut instant"

    # Put one of those short-history machines on top, which is exactly what happened
    # in the field and moved the reported instant back two days.
    reordered = sorted(real, key=lambda r: r["as_of"])
    monkeypatch.setattr(forecast_model, "score_fleet", lambda ids: reordered)

    out = await fleet.fleet_health()
    assert out["assets"][0]["as_of"] != configured
    assert out["as_of"] == configured


async def test_scoring_does_not_block_the_event_loop(monkeypatch):
    """The one recompute still has to stay off the loop, or the dashboard freezes."""

    def slow_score(in_service):
        time.sleep(0.3)
        return {"available": True, "as_of": None, "at_risk": 0, "fleet_size": 0, "assets": []}

    monkeypatch.setattr(fleet, "_score", slow_score)

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    beat = asyncio.create_task(ticker())
    await fleet.fleet_health()
    beat.cancel()

    # Run inline, the loop gets no turn at all and this stays at 1.
    assert ticks > 5, f"loop only ran {ticks} times during a 0.3s scoring"
