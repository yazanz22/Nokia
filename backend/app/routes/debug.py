import time

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..ml.client import fault_model
from ..nac import get_live_client, get_network_client
from ..nac.factory import FallbackNaCClient
from ..store import store

router = APIRouter(tags=["debug"])


@router.post("/nac/live-check")
async def nac_live_check(asset_id: str | None = None) -> dict:
    """Run a genuine CAMARA call against the Nokia sandbox, right now.

    This is the "prove it's real" button. It always hits the live API regardless of
    NAC_MODE, and returns the round-trip time so the latency is visible too.
    """
    settings = get_settings()
    client = get_live_client()
    if client is None:
        raise HTTPException(
            503, "live CAMARA client unavailable — set NAC_API_KEY in .env"
        )
    target = asset_id or next(iter(store.assets), "EQ-0001")
    device = settings.device_map().get(target) or settings.nac_default_device

    t0 = time.perf_counter()
    reach = await client.get_reachability(target)
    t_reach = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    loc = await client.get_location(target)
    t_loc = (time.perf_counter() - t1) * 1000

    return {
        "endpoint_host": settings.nac_api_host,
        "device": device,
        "device_status": {
            "path": "/device-status/device-reachability-status/v1/retrieve",
            "latency_ms": round(t_reach),
            "result": reach.model_dump(mode="json"),
        },
        "location_retrieval": {
            "path": "/location-retrieval/v0/retrieve",
            "latency_ms": round(t_loc),
            "result": loc.model_dump(mode="json"),
        },
    }


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
        "live_camara_available": get_live_client() is not None,
        "agent_mode": s.agent_mode,
        "llm_model": s.llm_model if s.agent_mode == "llm" else None,
        "ml_backend": fault_model.backend,
        "fleet_size": len(store.assets),
        "open_incidents": sum(1 for i in store.incidents.values() if i.closed_at is None),
    }
