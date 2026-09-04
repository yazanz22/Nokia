"""Two investigations at once must not send the same technician to both machines.

A judge injecting two faults in a row — two clicks, comfortably inside the 4/min
rate limit — runs two investigations concurrently. Each one asks CAMARA where the
crew are before it decides who goes, and that costs ~3.6s of serial round trips.
Read the free crew before those awaits and act on the answer after them, and both
investigations pick the same nearest technician: one person, two work orders, two
sites tens of kilometres apart.
"""

from __future__ import annotations

import asyncio

import pytest

from app.agent import run_investigation
from app.agent.tools import create_work_order
from app.models import FaultPrediction, utcnow
from app.nac.base import DeviceLocation
from app.simulator import simulator
from app.store import store


async def _investigate(asset_id: str) -> str:
    simulator.inject(asset_id, "hardware")
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    await run_investigation(inc.id)
    return inc.id


@pytest.mark.asyncio
async def test_two_investigations_do_not_share_a_technician():
    """The reported failure, reproduced: two assets, one crew, one clock."""
    first, second = sorted(store.assets)[:2]

    inc_a, inc_b = await asyncio.gather(_investigate(first), _investigate(second))

    orders = {
        wo.incident_id: wo
        for wo in store.work_orders.values()
        if wo.incident_id in (inc_a, inc_b)
    }
    assert len(orders) == 2, "both hardware faults should have produced a work order"

    a, b = orders[inc_a], orders[inc_b]
    assert a.technician_id and b.technician_id, "a dispatch with nobody on it is not a dispatch"
    assert a.technician_id != b.technician_id, (
        f"{a.id} ({a.asset_id}) and {b.id} ({b.asset_id}) were both assigned "
        f"{a.technician_name} — one technician cannot drive to two machines "
        f"{a.distance_km:.0f} km and {b.distance_km:.0f} km away"
    )

    # And the claim is reflected in the fleet state the dashboard renders, not just
    # in the two work orders.
    assert not store.technicians[a.technician_id].available
    assert not store.technicians[b.technician_id].available


@pytest.mark.asyncio
async def test_concurrent_work_orders_claim_distinct_technicians():
    """The same race at the point it actually happens, with the crew fully booked.

    One work order per technician, all raised at once. If the claim is not atomic the
    same person is chosen repeatedly and most of these orders name someone already
    driving elsewhere.
    """
    fault = FaultPrediction(
        asset_id="EQ-0001", mode="DEVICE_FAILURE", confidence=0.9,
        recommended_part="HYD-PUMP-40L",
    )
    loc = DeviceLocation(asset_id="EQ-0001", latitude=27.5, longitude=35.0,
                         accuracy_m=50.0, as_of=utcnow(), source="mock")

    crew = len(store.technicians)
    orders = await asyncio.gather(
        *(create_work_order(f"INC-{i}", f"EQ-{i:04d}", fault, loc) for i in range(crew))
    )

    assigned = [wo.technician_id for wo in orders if wo.technician_id]
    assert len(assigned) == crew, "every order should have found a free technician"
    assert len(set(assigned)) == crew, (
        f"{crew} concurrent dispatches shared {len(set(assigned))} technicians between them"
    )
    assert all(not t.available for t in store.technicians.values())
