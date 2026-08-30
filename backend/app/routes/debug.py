from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..ml.client import fault_model
from ..nac import get_network_client
from ..nac.factory import FallbackNaCClient
from ..store import store

router = APIRouter(tags=["debug"])


@router.get("/debug/nac")
async def debug_nac(asset_id: str) -> dict:
    """Prove a Network-as-Code call end to end. With NAC_MODE=live this hits the
    Nokia sandbox and returns source='live'."""
    if asset_id not in store.assets:
        raise HTTPException(404, f"unknown asset {asset_id}")
    client = get_network_client()
    reach = await client.get_reachability(asset_id)
    loc = await client.get_location(asset_id)
    return {
        "nac_mode": get_settings().nac_mode,
        "effective_source": getattr(client, "last_source", reach.source)
        if isinstance(client, FallbackNaCClient)
        else reach.source,
        "reachability": reach.model_dump(mode="json"),
        "location": loc.model_dump(mode="json"),
    }


@router.get("/debug/health")
def debug_health() -> dict:
    s = get_settings()
    return {
        "nac_mode": s.nac_mode,
        "agent_mode": s.agent_mode,
        "llm_model": s.llm_model if s.agent_mode == "llm" else None,
        "ml_backend": fault_model.backend,
        "fleet_size": len(store.assets),
        "open_incidents": sum(1 for i in store.incidents.values() if i.closed_at is None),
    }
