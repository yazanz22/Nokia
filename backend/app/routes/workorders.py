from fastapi import APIRouter, HTTPException

from ..store import store

router = APIRouter(tags=["work-orders"])


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
    store.complete_work_order(wo)
    store.publish_kpis()
    return {"ok": True, "work_order": wo.model_dump(mode="json")}


@router.delete("/work-orders/{work_order_id}")
def delete_work_order(work_order_id: str) -> dict:
    """Cancel and remove a job, releasing the technician and the machine."""
    wo = store.work_orders.get(work_order_id)
    if wo is None:
        raise HTTPException(404, f"unknown work order {work_order_id}")
    store.delete_work_order(wo)
    store.publish_kpis()
    return {"ok": True, "id": work_order_id}
