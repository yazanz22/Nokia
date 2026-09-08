from fastapi import APIRouter, HTTPException

from ..models import WorkOrder
from ..store import store

router = APIRouter(tags=["work-orders"])


def _reject_if_settling(wo: WorkOrder, action: str) -> None:
    """Refuse to touch a work order the agent has not finished dispatching.

    Between ``add_work_order`` and the incident close there is one trace step — 0.7s —
    during which the card is on the dashboard and the investigation is still going to
    write the asset's state. Cancelling in there stranded the machine: the route set it
    back to ``healthy`` and freed the technician, and the investigation immediately
    overwrote that with ``dispatched`` and closed the incident against a work order that
    had just been deleted. The freshness sweep skips ``dispatched``, so the asset was
    left permanently un-investigated with nothing en route.

    Refusing, rather than having the route settle the asset and the incident itself:
    the investigation writes *after* us, so anything we settle here it simply overwrites
    a fraction of a second later — the route cannot win a race it is already behind in,
    and "cancel it, then let the agent re-mark it dispatched" is the exact bug. Each
    incident has one writer while it is open, and that is the agent. From outside, the
    only coherent answer is to wait for it to finish; the window is sub-second, and the
    409 says so, so the operator's second click lands on a work order that is fully
    formed and cancels cleanly.
    """
    if store.dispatch_in_flight(wo):
        raise HTTPException(
            409,
            f"{wo.id} is still being dispatched — the agent has not finished closing "
            f"{wo.incident_id}. Retry in a moment; {action} now would leave "
            f"{wo.asset_id} marked dispatched with nobody on the way.",
        )


@router.get("/work-orders")
def list_work_orders() -> dict:
    return {
        "work_orders": [
            w.model_dump(mode="json")
            for w in sorted(store.work_orders.values(), key=lambda x: x.created_at, reverse=True)
        ]
    }


@router.post("/work-orders/{work_order_id}/complete")
def complete_work_order(work_order_id: str) -> dict:
    """Sign a job off by hand.

    The simulator closes jobs on a timer so an unattended dashboard keeps running, but
    on stage the operator decides when the repair is done — and waiting out the timer
    mid-narration is worse than useless.
    """
    wo = store.work_orders.get(work_order_id)
    if wo is None:
        raise HTTPException(404, f"unknown work order {work_order_id}")
    if wo.status == "completed":
        raise HTTPException(409, f"{work_order_id} is already completed")
    _reject_if_settling(wo, "completing it")
    store.complete_work_order(wo)
    store.publish_kpis()
    return {"ok": True, "work_order": wo.model_dump(mode="json")}


@router.post("/work-orders/{work_order_id}/no-fault-found")
def close_no_fault_found(work_order_id: str) -> dict:
    """Close a job the technician attended without finding anything to repair.

    Distinct from completing it and from cancelling it. Completing says the part was
    fitted; cancelling says nobody went. This says somebody went, the diagnosis was
    wrong, and the part is coming back to the depot unused.
    """
    wo = store.work_orders.get(work_order_id)
    if wo is None:
        raise HTTPException(404, f"unknown work order {work_order_id}")
    if wo.status == "completed":
        raise HTTPException(409, f"{work_order_id} is already closed")
    if wo.technician_id is None:
        raise HTTPException(
            409,
            f"{work_order_id} has nobody assigned, so nobody attended it. Cancel it "
            f"instead: no fault found means a technician made the journey.",
        )
    _reject_if_settling(wo, "closing it")
    store.close_no_fault_found(wo)
    store.publish_kpis()
    return {"ok": True, "work_order": wo.model_dump(mode="json")}


@router.delete("/work-orders/{work_order_id}")
def delete_work_order(work_order_id: str) -> dict:
    """Cancel and remove a job, releasing the technician and the machine."""
    wo = store.work_orders.get(work_order_id)
    if wo is None:
        raise HTTPException(404, f"unknown work order {work_order_id}")
    _reject_if_settling(wo, "cancelling it")
    store.delete_work_order(wo)
    store.publish_kpis()
    return {"ok": True, "id": work_order_id}
