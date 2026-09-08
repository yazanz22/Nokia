"""The planned half of maintenance: preventive services and predictive repairs.

The corrective path has its own machinery — an incident, an agent, a network verdict —
and lives in ``routes/incidents.py`` and ``agent/``. Nothing here has broken.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from ..agent.tools import create_scheduled_work_order
from ..maintenance import (
    DUE_SOON_HOURS,
    bundle_candidates,
    scheduled_for,
    service_board,
    service_state,
)
from ..ml.forecast import forecast_model
from ..seed import SERVICE_KIT_PART
from ..store import store
from .fleet import fleet_health

router = APIRouter(tags=["maintenance"])


@router.get("/maintenance/schedule")
async def schedule(include_ok: bool = False) -> dict:
    """The service board, plus the machines where a service and a forecast coincide.

    Both halves in one response because the interesting row is the one that appears in
    both: a machine due a service *and* trending toward a failure is a single visit,
    and an operator looking at two separate screens never sees it.
    """
    health = await fleet_health()
    rows = health.get("assets", []) if health.get("available") else []
    board = service_board(include_ok=include_ok)
    # bundle_candidates asks the component model once per candidate machine. That is a
    # handful of scikit-learn calls, not a fleet scoring — but it is still synchronous
    # CPU work, and this route is async, so it goes to a worker thread rather than
    # stalling the event loop and with it every open dashboard's websocket.
    bundles = await asyncio.to_thread(bundle_candidates, rows)
    return {
        "due_soon_hours": DUE_SOON_HOURS,
        "service_part": SERVICE_KIT_PART,
        "overdue": sum(1 for r in board if r["state"] == "overdue"),
        "due_soon": sum(1 for r in board if r["state"] == "due_soon"),
        "assets": board,
        "bundles": bundles,
        "forecast_available": bool(health.get("available")),
    }


@router.post("/maintenance/{asset_id}/preventive")
async def raise_preventive(asset_id: str) -> dict:
    """Schedule the machine's due service.

    Refused when the machine is not actually due. A preventive job on a machine 400
    hours from its interval is not preventive maintenance, it is a wasted visit — the
    exact thing the rest of this system exists to stop.
    """
    asset = store.assets.get(asset_id)
    if asset is None:
        raise HTTPException(404, f"no asset {asset_id}")
    if service_state(asset) == "ok":
        raise HTTPException(
            409,
            f"{asset_id} is {asset.service_due_in_hours:.0f} h from its next service — "
            f"nothing is due. Services are raised inside {DUE_SOON_HOURS:.0f} h of the "
            f"interval.",
        )
    if scheduled_for(asset_id):
        raise HTTPException(409, f"{asset_id} already has a scheduled visit open")

    wo = await create_scheduled_work_order(
        asset_id,
        "preventive",
        [SERVICE_KIT_PART],
        reason=f"{asset.service_interval_hours:.0f}-hour service",
    )
    return wo.model_dump(mode="json")


@router.post("/maintenance/{asset_id}/predictive")
async def raise_predictive(asset_id: str, bundle_service: bool = False) -> dict:
    """Schedule a repair on a machine the forecast expects to fail.

    ``bundle_service`` folds the machine's due service into the same visit — one
    journey, one loading stop, one mobilisation instead of two of each. Only accepted
    when the service is genuinely due; bundling a service that is 300 hours away is
    just servicing early and pretending it was free.
    """
    asset = store.assets.get(asset_id)
    if asset is None:
        raise HTTPException(404, f"no asset {asset_id}")
    if scheduled_for(asset_id):
        raise HTTPException(409, f"{asset_id} already has a scheduled visit open")
    if not forecast_model.available:
        raise HTTPException(503, "the forecast model is not loaded")

    identified = forecast_model.identify_component(asset_id)
    if identified is None:
        raise HTTPException(
            409,
            f"the component model has no opinion on {asset_id} — most often a workshop "
            f"repair gap inside its trailing window, where a score would be computed "
            f"across a rebuild. No part can be named, so no visit is scheduled.",
        )
    component, confidence = identified
    from ..seed import COMPONENT_PARTS

    part = COMPONENT_PARTS.get(component, ("", 0))[0]
    if not part:
        raise HTTPException(409, f"no part mapped for component {component}")

    if bundle_service and service_state(asset) == "ok":
        raise HTTPException(
            409,
            f"{asset_id} is {asset.service_due_in_hours:.0f} h from its service — there "
            f"is nothing to bundle.",
        )
    bundled = bool(bundle_service)
    parts = [part] + ([SERVICE_KIT_PART] if bundled else [])

    wo = await create_scheduled_work_order(
        asset_id,
        "predictive",
        parts,
        component=component,
        component_confidence=confidence,
        bundled_service=bundled,
        reason="forecast failure" + (" + due service" if bundled else ""),
    )
    return wo.model_dump(mode="json")
