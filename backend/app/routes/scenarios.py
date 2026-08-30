from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..anomaly import detector
from ..events import bus
from ..models import WsEvent
from ..simulator import simulator
from ..simulator.engine import SCENARIOS
from ..store import store

router = APIRouter(tags=["scenarios"])


class InjectRequest(BaseModel):
    asset_id: str
    scenario: str  # "blindspot" | "hardware" | "sensor"


@router.get("/scenarios")
def list_scenarios() -> dict:
    return {
        "scenarios": list(SCENARIOS.keys()),
        "eligible_assets": [a.id for a in store.assets.values() if a.state in ("healthy", "anomaly")],
    }


@router.post("/scenarios/inject")
def inject_scenario(req: InjectRequest) -> dict:
    if req.asset_id not in store.assets:
        raise HTTPException(404, f"unknown asset {req.asset_id}")
    if req.scenario not in SCENARIOS:
        raise HTTPException(422, f"unknown scenario {req.scenario!r}; try {list(SCENARIOS)}")
    label = simulator.inject(req.asset_id, req.scenario)
    return {"ok": True, "asset_id": req.asset_id, "scenario": req.scenario, "dataset_label": label}


@router.post("/scenarios/reset")
async def reset_demo() -> dict:
    store.reset()
    simulator.reseed()
    detector.reset()
    bus.publish(WsEvent(type="snapshot", payload=store.snapshot()))
    return {"ok": True, "fleet_size": len(store.assets)}
