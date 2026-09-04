from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from ..config import get_settings
from ..ml.forecast import forecast_model
from ..store import store

router = APIRouter(tags=["fleet"])

# ── forecast cache ──────────────────────────────────────────────────────────
#
# Scoring the fleet costs ~0.48s of scikit-learn (~2.5s on the first call, which also
# parses 33k rows of telemetry history), and the dashboard asks for it every 30
# seconds per open tab. Every one of those calls used to redo the whole thing and
# arrive at exactly the same numbers, because the only input that moves is the fleet
# roster: `_history()` is cut at the configured FORECAST_AS_OF and lru_cached, the
# models are loaded once at import, and no live telemetry ever reaches either. Two
# tabs open through a ten-minute demo is forty pointless fleet scorings.
#
# What actually invalidates the answer is the roster this endpoint scores, not the
# passage of time. The endpoint only scores machines still in service, so:
#   * a machine dispatched, gone silent or ruled a blindspot drops out of the roster
#     and must drop out of the panel — a process-lifetime cache would keep showing
#     the excavator a technician is already driving to;
#   * a machine that comes back from a work order rejoins it and must reappear — a
#     process-lifetime cache would leave it absent for the rest of the session;
#   * label and site are stamped onto the rows from the store, so a fleet rebuilt by
#     a reset with different machines has to be scored again.
# The key below is exactly that: the in-service roster with the fields we copy off it,
# plus the as-of instant the whole forecast is cut at. A healthy->anomaly flip does not
# change it, and correctly so — both states are in service and the history behind the
# score is identical either way. A reset that rebuilds the same fleet does not change
# it either, which is the point: nothing about the answer moved.
_cache_key: tuple[Any, ...] | None = None
_cache_value: dict | None = None
# Tabs poll on the same 30s cadence and land together. Without this the first poll of
# a new roster is scored once per tab, in parallel, for one shared answer.
_cache_lock = asyncio.Lock()


def _roster_key(in_service: list[str]) -> tuple[Any, ...]:
    rows = []
    for aid in sorted(in_service):
        asset = store.assets.get(aid)
        rows.append((aid, asset.label, asset.site) if asset else (aid, None, None))
    return (get_settings().forecast_as_of, tuple(rows))


def _score(in_service: list[str]) -> dict:
    """The expensive half. Runs in a worker thread — never on the event loop."""
    scored = forecast_model.score_fleet(in_service)
    for row in scored:
        asset = store.assets.get(row["asset_id"])
        if asset:
            row["label"] = asset.label
            row["site"] = asset.site

    # `as_of` is a property of the forecast, not of whichever machine happens to rank
    # first. It used to be read off scored[0] — the top-ranked row — so the fleet
    # timestamp moved when the ranking moved: it read 2026-08-17T06:00:00 instead of
    # 2026-08-18T06:00:00 purely because a machine whose history ends two days early
    # took the top slot. Three of the thirty assets end before the cutoff, so this was
    # one re-rank away at any time.
    #
    # The configured instant is the right answer rather than max() across rows: it is
    # where the history was cut, which is the "now" every row was scored against,
    # including the rows whose last reading is older. max() would answer with the
    # newest reading anyone happens to have, so a fleet where every late-reporting
    # machine is out for repair would silently report an earlier "now" than the one the
    # model actually used. max() is kept only as the fallback for an unset setting,
    # where there is no configured instant to report.
    as_of = get_settings().forecast_as_of or (
        max(s["as_of"] for s in scored) if scored else None
    )
    return {
        "available": True,
        "as_of": as_of,
        "at_risk": sum(1 for s in scored if s["at_risk"]),
        "fleet_size": len(scored),
        "assets": scored,
    }


@router.get("/fleet/health")
async def fleet_health() -> dict:
    """Predictive maintenance view: which machines are trending toward failure.

    Nothing here has broken yet — this is the proactive half of the system, the
    counterpart to the reactive incident flow.
    """
    global _cache_key, _cache_value

    if not forecast_model.available:
        return {"available": False, "assets": [], "at_risk": 0}

    # Only machines that are still in service get scored. A forecast is a claim about
    # a machine that is running now and will not be later; once an asset has gone
    # silent, been confirmed a blindspot, or had a technician dispatched to it, that
    # claim is already settled and the row is no longer a prediction. During the demo
    # this was literal: the excavator the agent had just diagnosed and dispatched
    # reappeared as a sixth row in the predictive panel, ringed on the map, while the
    # narration said the panel holds machines that have not failed. "healthy" and
    # "anomaly" are the two states where the machine is still reporting and no
    # incident is open against it — everything else belongs to the reactive half.
    in_service = [aid for aid, a in store.assets.items() if a.state in ("healthy", "anomaly")]
    key = _roster_key(in_service)
    if _cache_key == key and _cache_value is not None:
        return _cache_value

    async with _cache_lock:
        # Re-read the roster under the lock: whoever held it may have just scored the
        # answer we want, and if the fleet moved while we were queued we want the
        # roster as it is now rather than the one we walked in with.
        in_service = [aid for aid, a in store.assets.items() if a.state in ("healthy", "anomaly")]
        key = _roster_key(in_service)
        if _cache_key == key and _cache_value is not None:
            return _cache_value

        # Off the event loop, for the same reason the fault classifier is: this is
        # half a second of CPU-bound scikit-learn, and run inline it stalls the
        # simulator tick, the anomaly detector and every websocket send with it. With
        # the cache in front it happens once per roster instead of once per poll, but
        # that one call still freezes the dashboard if it runs here.
        value = await asyncio.to_thread(_score, in_service)
        _cache_key, _cache_value = key, value
        return value


def _reset_cache() -> None:
    """Drop the memoised forecast. For tests — nothing in the app needs it."""
    global _cache_key, _cache_value
    _cache_key, _cache_value = None, None
