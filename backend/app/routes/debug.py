import logging
import time

from fastapi import APIRouter, HTTPException, Request

from ..config import get_settings
from ..ml.client import fault_model
from ..nac import get_live_client, get_network_client
from ..nac.factory import FallbackNaCClient
from ..ratelimit import live_check_limiter
from ..store import store

log = logging.getLogger("nac.geofence")
router = APIRouter(tags=["debug"])


@router.post("/nac/live-check")
async def nac_live_check(request: Request, asset_id: str | None = None) -> dict:
    """Run a genuine CAMARA call against the Nokia sandbox, right now.

    This is the "prove it's real" button. It always hits the live API regardless of
    NAC_MODE, and returns the round-trip time so the latency is visible too.
    """
    live_check_limiter.check(request)
    settings = get_settings()
    client = get_live_client()
    if client is None:
        raise HTTPException(
            503, "live CAMARA client unavailable — set NAC_API_KEY in .env"
        )
    if asset_id and asset_id not in store.assets:
        raise HTTPException(404, f"unknown asset {asset_id}")
    target = asset_id or next(iter(store.assets), "EQ-0001")
    device = settings.device_map().get(target) or settings.nac_default_device

    t0 = time.perf_counter()
    reach = await client.get_reachability(target)
    t_reach = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    loc = await client.get_location(target)
    t_loc = (time.perf_counter() - t1) * 1000

    # Geofencing Subscriptions: list first, register only if the site has none. Best
    # effort — this panel exists to show the other calls too, and a subscription
    # failure must not take the whole proof down with it.
    geofence: dict = {"path": "/geofencing-subscriptions/v0.3/subscriptions"}
    try:
        existing = await client._post_list_subscriptions()  # type: ignore[attr-defined]
        if existing:
            geofence.update(status="existing", count=len(existing),
                            subscription_id=existing[0].get("id"))
        else:
            sink = str(request.base_url).rstrip("/") + "/api/nac/geofence-callback"
            created = await client.create_geofence_subscription(sink)  # type: ignore[attr-defined]
            geofence.update(status="created", subscription_id=created.get("id"), sink=sink)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        if "INVALID_SINK" in detail or "callback host" in detail:
            # Expected when running locally. The operator will only accept a sink it
            # can actually reach, which is the API behaving correctly rather than a
            # fault — say so instead of showing a raw 400.
            geofence.update(
                status="needs public url",
                note=(
                    "The operator rejects a callback it cannot reach, so registering a "
                    "perimeter watch works from the deployed URL and not from localhost."
                ),
            )
        else:
            geofence.update(status="unavailable", error=f"{type(exc).__name__}: {detail}"[:160])

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
        # The fourth family, and the only one that pushes. Registering the perimeter is
        # what a real deployment does once at startup; here it runs on request so the
        # call is visible. Reuses an existing subscription rather than creating one per
        # click — a proof panel should not quietly accumulate state in someone's
        # operator account.
        "geofencing": geofence,
        # Issued as part of the reachability step rather than on its own, so there is
        # no separate round-trip to report and we do not invent one. Named here
        # because it is a distinct CAMARA API and the panel exists to show exactly
        # which ones this really calls.
        "congestion_insights": {
            "path": "/congestion-insights/v0/query",
            "bundled_with": "device_status",
            "result": {
                "congestion_level": reach.congestion_level,
                "confidence_level": reach.congestion_confidence,
            },
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
    import app.agent as agent_mod
    from ..agent.memory import memory

    s = get_settings()
    return {
        "nac_mode": s.nac_mode,
        "live_camara_available": get_live_client() is not None,
        "agent_mode": s.agent_mode,
        "llm_model": s.llm_model if s.agent_mode == "llm" else None,
        # Which agent actually ran last. If AGENT_MODE=llm but this says
        # "rule (fallback)", the model is not running — check last_agent_error.
        "last_agent_used": agent_mod.last_agent_used,
        "last_agent_error": agent_mod.last_agent_error,
        "ml_backend": fault_model.backend,
        "memory_episodes": memory.size,
        "fleet_size": len(store.assets),
        "open_incidents": sum(1 for i in store.incidents.values() if i.closed_at is None),
    }


@router.post("/nac/geofence-callback")
async def geofence_callback(event: dict) -> dict:
    """Sink for CAMARA Geofencing Subscriptions.

    Registering a subscription means handing the operator a URL it will POST to, so
    this has to exist and answer — pointing a real subscription at a 404 would be
    claiming an integration we had not finished.

    The demo fleet's crossings are evaluated against the simulation and never arrive
    here; what would arrive is the sandbox test SIM leaving the registered area. We
    accept it, log it, and acknowledge, which is the whole contract.
    """
    log.info("geofence callback: %s", str(event)[:300])
    return {"received": True}
