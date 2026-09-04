from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..agent.memory import memory
from ..anomaly import detector
from ..events import bus
from ..models import WsEvent
from ..ratelimit import RateLimiter, inject_budget, inject_limiter
from ..simulator import simulator
from ..simulator.engine import DRIFT_SCENARIO, SCENARIOS
from ..store import store

router = APIRouter(tags=["scenarios"])

# Reset is the one state-changing endpoint that spends no external quota — no LLM
# tokens, no sandbox calls — so what needs protecting is the demo board itself, not a
# budget. A `while true; do curl -XPOST .../scenarios/reset; done` against the public
# URL wipes the fleet faster than anything can appear on it, and a judge watching sees
# a permanently blank dashboard with no error to explain it.
#
# Hence a per-client limiter and deliberately *not* a DailyBudget: a process-wide
# ceiling is keyed on nothing, so a stranger burning it through would leave the
# presenter unable to reset at all — the protection would finish the attack. Keyed per
# client, the presenter's own bucket is untouched by whatever anyone else is doing.
#
# Ten a minute is far past legitimate use — a rehearsal reset is followed by a minute
# of demo, and the documented `?clear_memory=true` pre-demo step is a single call — so
# no presenter, however jumpy the clicking, can run into this.
reset_limiter = RateLimiter(limit=10, window_seconds=60.0, name="fleet reset")


class InjectRequest(BaseModel):
    asset_id: str
    scenario: str  # "blindspot" | "hardware" | "sensor"


@router.get("/scenarios")
def list_scenarios() -> dict:
    # Only healthy assets, matching the guard in inject() below. This list used to
    # include `anomaly` too, which advertised assets that inject answers with a 409 —
    # and the 409 is right: injecting over an already-dark asset overwrites its pending
    # dataset label mid-investigation (see the comment in inject), and an `offsite`
    # drift on a silent asset does nothing at all, because the simulator skips silent
    # assets before it reaches the drift branch, so the machine never moves and the
    # geofence never fires. Offering a target that cannot work is worse than offering
    # none. The dashboard's own picker already filters on healthy; this endpoint was
    # the outlier.
    return {
        "scenarios": [*SCENARIOS.keys(), DRIFT_SCENARIO],
        "eligible_assets": [a.id for a in store.assets.values() if a.state == "healthy"],
    }


@router.post("/scenarios/inject")
def inject_scenario(req: InjectRequest, request: Request) -> dict:
    inject_limiter.check(request)
    inject_budget.check()
    asset = store.assets.get(req.asset_id)
    if asset is None:
        raise HTTPException(404, f"unknown asset {req.asset_id}")
    if req.scenario not in SCENARIOS and req.scenario != DRIFT_SCENARIO:
        raise HTTPException(
            422,
            f"unknown scenario {req.scenario!r}; try {[*SCENARIOS, DRIFT_SCENARIO]}",
        )
    # Injecting over an asset that is already dark would swap the dataset label
    # underneath a running investigation — the agent would read device status for
    # one fault and classify a different one. A double-clicked button must not be
    # able to produce a self-contradicting result on stage.
    # A machine already off site is still perfectly healthy, so the healthy-state
    # guard below would happily start a second drift on it. Refuse that instead.
    if req.scenario == DRIFT_SCENARIO and asset.offsite:
        raise HTTPException(409, f"{req.asset_id} has already left the site perimeter")
    if asset.state != "healthy":
        raise HTTPException(
            409,
            f"{req.asset_id} is already {asset.state} — reset the fleet or pick another asset",
        )
    label = simulator.inject(req.asset_id, req.scenario)
    return {"ok": True, "asset_id": req.asset_id, "scenario": req.scenario, "dataset_label": label}


@router.post("/scenarios/reset")
async def reset_demo(request: Request, clear_memory: bool = False) -> dict:
    """Reset the fleet.

    Agent memory is kept by default: the fleet is demo state, but what the agent has
    learned about which parts of the site swallow signal is knowledge, and throwing it
    away on every reset would make the system permanently amnesiac. Pass
    ``clear_memory=true`` for a genuinely blank slate — e.g. before recording a demo.
    """
    # Before anything is touched, so a refused reset changes no state at all. This is a
    # rate limit and not a lock: reset stays reachable while an investigation is in
    # flight, which is exactly what store.epoch is for — the reset bumps the epoch and
    # the in-flight run discards its own result rather than writing it onto a fresh
    # fleet. Blocking reset during a run would strand a presenter behind a demo that
    # went wrong.
    reset_limiter.check(request)
    # The tick loop prunes the two limiters it knows about; this one is only ever
    # touched here, so it sweeps its own buckets. Otherwise a public URL grows the dict
    # by one dead entry per crawler, forever.
    reset_limiter.prune()
    store.reset()
    simulator.reseed()
    detector.reset()
    if clear_memory:
        memory.clear()
    bus.publish(WsEvent(type="snapshot", payload=store.snapshot()))
    return {
        "ok": True,
        "fleet_size": len(store.assets),
        "memory_episodes": memory.size,
    }
