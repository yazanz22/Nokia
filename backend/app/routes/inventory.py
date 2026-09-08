"""Warehouse stock: what each depot holds, and what an operator can do about it."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..seed import PART_LABELS, PART_REORDER_AT, VAN_STOCK
from ..store import store

router = APIRouter(tags=["inventory"])

# A depot cannot hold an unbounded number of anything, and an operator who fat-fingers
# a restock should be told so rather than silently creating four hundred alternators.
MAX_STOCK_PER_PART = 99


def _part_row(part: str, units: int) -> dict:
    reorder_at = PART_REORDER_AT.get(part, 0)
    return {
        "part": part,
        "label": PART_LABELS.get(part, part),
        "units": units,
        "reorder_at": reorder_at,
        # "low" is at or below the reorder point rather than under it: a depot holding
        # exactly its last alternator is the case worth flagging, not the one after.
        "low": units <= reorder_at,
        "out": units <= 0,
    }


@router.get("/inventory")
def inventory() -> dict:
    """Every depot, its stock, and what is running short.

    Fleet-wide totals are computed here rather than in the dashboard because "do we
    have one anywhere" and "does *this* depot have one" are different questions and
    only the second is answerable from a single row — a part can be comfortably stocked
    across the site and still be missing from the depot that matters.
    """
    depots = []
    totals: dict[str, int] = {}
    for wh in store.warehouses.values():
        rows = [_part_row(p, u) for p, u in sorted(wh.stock.items())]
        for p, u in wh.stock.items():
            totals[p] = totals.get(p, 0) + u
        depots.append(
            {
                "id": wh.id,
                "name": wh.name,
                "latitude": wh.latitude,
                "longitude": wh.longitude,
                "parts": rows,
                "low_count": sum(1 for r in rows if r["low"]),
            }
        )
    return {
        "warehouses": depots,
        "fleet_totals": [_part_row(p, u) for p, u in sorted(totals.items())],
        # What rides in the van and therefore never appears on a shelf. Listed so the
        # inventory view can say why a sensor kit is not in it, rather than looking
        # like an omission.
        "van_stock": list(VAN_STOCK),
    }


class StockAdjustment(BaseModel):
    part: str
    # Signed: positive receipts a delivery, negative writes stock off. Both are things
    # a storeman does, and expressing them as one operation keeps the audit shape
    # identical for each.
    delta: int = Field(..., ge=-MAX_STOCK_PER_PART, le=MAX_STOCK_PER_PART)


@router.post("/inventory/{warehouse_id}/adjust")
def adjust_stock(warehouse_id: str, body: StockAdjustment) -> dict:
    """Receipt a delivery or write stock off at one depot.

    Deliberately not a "set to N" endpoint. Stock moves by events — a delivery arrived,
    a unit was damaged — and a blind overwrite loses the race against a dispatch that
    claimed a unit while the operator was typing: the write-back would put it straight
    back on the shelf and two jobs would leave with one alternator. A delta commutes
    with a concurrent claim, so it cannot.
    """
    wh = store.warehouses.get(warehouse_id)
    if wh is None:
        raise HTTPException(404, f"no depot {warehouse_id}")
    part = body.part
    if part in VAN_STOCK:
        raise HTTPException(
            400,
            f"{part} rides in the van rather than living on a shelf — there is no depot "
            f"stock of it to adjust.",
        )
    current = wh.stock.get(part, 0)
    new = current + body.delta
    if new < 0:
        raise HTTPException(
            409,
            f"{wh.name} holds {current} x {part}; cannot write off {abs(body.delta)}.",
        )
    if new > MAX_STOCK_PER_PART:
        raise HTTPException(400, f"stock cap is {MAX_STOCK_PER_PART} per part per depot")
    wh.stock[part] = new
    store.publish_warehouses()
    return {"warehouse_id": wh.id, "part": part, "units": new}
