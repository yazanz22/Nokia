from fastapi import APIRouter

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
