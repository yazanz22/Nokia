from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..agent.memory import memory
from ..anomaly import detector
from ..events import bus
from ..models import WsEvent
from ..ratelimit import inject_limiter
from ..simulator import simulator
from ..simulator.engine import DRIFT_SCENARIO, SCENARIOS
from ..store import store

router = APIRouter(tags=["scenarios"])


class InjectRequest(BaseModel):
    asset_id: str
    scenario: str  # "blindspot" | "hardware" | "sensor"


@router.get("/scenarios")
def list_scenarios() -> dict:
    return {
        "scenarios": [*SCENARIOS.keys(), DRIFT_SCENARIO],
        "eligible_assets": [a.id for a in store.assets.values() if a.state in ("healthy", "anomaly")],
    }


@router.post("/scenarios/inject")
def inject_scenario(req: InjectRequest, request: Request) -> dict:
    inject_limiter.check(request)
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
async def reset_demo(clear_memory: bool = False) -> dict:
    """Reset the fleet.

    Agent memory is kept by default: the fleet is demo state, but what the agent has
    learned about which parts of the site swallow signal is knowledge, and throwing it
    away on every reset would make the system permanently amnesiac. Pass
    ``clear_memory=true`` for a genuinely blank slate — e.g. before recording a demo.
    """
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
