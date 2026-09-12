import logging
import time

from fastapi import APIRouter, HTTPException, Request

from ..agent.tools import MIN_CONGESTION_CONFIDENCE
from ..config import get_settings
from ..ml.client import fault_model
from ..nac import get_live_client, get_network_client
from ..nac.factory import FallbackNaCClient
from ..ratelimit import inject_budget, live_check_budget, live_check_limiter
from ..store import store

log = logging.getLogger("nac.geofence")
router = APIRouter(tags=["debug"])

GEOFENCE_CALLBACK_PATH = "/api/nac/geofence-callback"
# Two different ways a perimeter watch goes unregistered, told apart on purpose. They
# used to share one sentence - "works from the deployed URL and not from localhost" -
# which was wrong for both on a deployed service: there it can only mean the setting
# is missing, or the address in it was refused, and those are different fixes.
#
# Nothing sent: no public address is configured, so there is no callback to hand over.
NEEDS_PUBLIC_URL = (
    "Registering a perimeter watch hands the operator a callback address, so it needs "
    "PUBLIC_BASE_URL set to this deployment's own public URL. Unset, nothing is "
    "registered: expected on localhost, a missing setting anywhere else."
)
# Something sent and refused: an address is configured and the operator turned it down.
SINK_REJECTED = (
    "The operator refused the callback address this deployment is configured with, so "
    "no perimeter watch was registered. PUBLIC_BASE_URL has to be this service's own "
    "public https address."
)
# Congestion is the one family here that can come back empty on its own — the adapter
# issues it best-effort so it can never fail the reachability answer beside it. The
# panel used to render nothing at all in that case, which quietly removed the API that
# carries the whole coverage argument. Say it out loud instead, and say what it is not:
# "None" is a level the operator states and it means the opposite of this.
CONGESTION_NO_READING = (
    "The query ran alongside the reachability call and came back without a reading we "
    "could use, so the agent judges this silence on the other signals. Not the same as "
    "a clear area — the operator grades that as level 'None'."
)


@router.post("/nac/live-check")
async def nac_live_check(request: Request, asset_id: str | None = None) -> dict:
    """Run a genuine CAMARA call against the Nokia sandbox, right now.

    This is the "prove it's real" button. It always hits the live API regardless of
    NAC_MODE, and returns the round-trip time so the latency is visible too.
    """
    live_check_limiter.check(request)
    live_check_budget.check()
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
    sink: str | None = None
    try:
        existing = await client._post_list_subscriptions()  # type: ignore[attr-defined]
        if existing:
            geofence.update(status="existing", count=len(existing),
                            subscription_id=existing[0].get("id"))
        else:
            # From configuration, never from the request. A sink is a URL the operator
            # will POST to on our credentials, and request.base_url comes from the Host
            # header — which is written by whoever called this open, public endpoint.
            # Building it from there would let a caller register a subscription on our
            # real Nokia account pointing at their server. Unset means we have no
            # public address we can vouch for, and the honest answer is to register
            # nothing rather than to guess.
            sink = settings.public_url(GEOFENCE_CALLBACK_PATH)
            if sink is None:
                geofence.update(
                    status="needs public url",
                    note=NEEDS_PUBLIC_URL,
                    detail=(
                        "PUBLIC_BASE_URL is not set to an absolute http(s) URL, so no "
                        "callback address was sent to the operator."
                    ),
                )
            else:
                created = await client.create_geofence_subscription(sink)  # type: ignore[attr-defined]
                geofence.update(status="created", subscription_id=created.get("id"), sink=sink)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        if "INVALID_SINK" in detail or "callback host" in detail:
            # A sink was built from PUBLIC_BASE_URL and the operator refused it. This was
            # once labelled "expected when running locally", from before the sink stopped
            # coming from the Host header. Locally PUBLIC_BASE_URL is unset and the branch
            # above answers first, so arriving here means a configured address was turned
            # down - a different fix from never setting one - and the panel now says
            # which, with the address that was actually sent.
            geofence.update(
                status="sink rejected",
                note=SINK_REJECTED,
                detail=(f"Sent {sink}. Operator replied: {detail}" if sink else detail)[:240],
            )
        else:
            geofence.update(status="unavailable", error=f"{type(exc).__name__}: {detail}"[:160])

    # Congestion Insights rides along inside the reachability call above: the adapter
    # reports the (level, confidence) pair or neither — ``parse_congestion`` refuses a
    # level with no stated confidence behind it — and swallows the reason, because it is
    # best-effort by design and must not take the primary answer down with it. So an
    # absent level here means the query did not return a reading we could use, and that
    # is a different fact from a serving area the operator grades as clear. Both used to
    # leave the panel with a bare null and no way to tell them apart.
    #
    # Inferred rather than reported, and worth naming as such: the exception itself
    # stays in the adapter, logged under "nac.live". Rerunning the call here to capture
    # it would spend a second sandbox query per click and make ``bundled_with`` a lie.
    congestion: dict = {
        "path": "/congestion-insights/v0/query",
        "bundled_with": "device_status",
        # Always attempted — it is part of the reachability step, not a call this
        # endpoint chooses to make — so the panel can say the call happened either way.
        "attempted": True,
        "returned": reach.congestion_level is not None,
        # The floor ``assess_silence`` actually applies, sent rather than restated in
        # the UI. The panel explains the agent's behaviour, so it has to quote the
        # agent's number; a threshold written down in two places is one that drifts.
        "min_confidence": MIN_CONGESTION_CONFIDENCE,
        "result": {
            "congestion_level": reach.congestion_level,
            "confidence_level": reach.congestion_confidence,
        },
    }
    if not congestion["returned"]:
        congestion["note"] = CONGESTION_NO_READING

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
        "congestion_insights": congestion,
    }


@router.get("/debug/nac")
async def debug_nac(asset_id: str, request: Request) -> dict:
    """Prove a Network-as-Code call end to end. With NAC_MODE=live this hits the
    Nokia sandbox and returns source='live'."""
    # In live mode this spends sandbox quota exactly like the live-check panel does,
    # and it was the one money-spending endpoint left wide open.
    live_check_limiter.check(request)
    live_check_budget.check()
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
    # A provider exception is written for a developer's terminal: it can carry the
    # request URL, headers and fragments of the body it was rejecting. This endpoint
    # is open on a public deploy, so it gets a bounded prefix — enough to tell a 429
    # from a 404 from a bad model name, and no more. The same 160 characters the
    # geofence branch above allows itself. A bound, not a redaction: nothing genuinely
    # secret should be in an exception message in the first place.
    agent_error = agent_mod.last_agent_error
    return {
        "nac_mode": s.nac_mode,
        "live_camara_available": get_live_client() is not None,
        "agent_mode": s.agent_mode,
        "llm_model": s.llm_model if s.agent_mode == "llm" else None,
        # Which agent actually ran last. If AGENT_MODE=llm but this says
        # "rule (fallback)", the model is not running — check last_agent_error.
        "last_agent_used": agent_mod.last_agent_used,
        "last_agent_error": str(agent_error)[:160] if agent_error else None,
        "ml_backend": fault_model.backend,
        "memory_episodes": memory.size,
        "scenario_budget_remaining": inject_budget.remaining,
        "live_check_budget_remaining": live_check_budget.remaining,
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
