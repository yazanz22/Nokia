"""A wrong diagnosis has to be reversible, and the part has to come back.

The system's whole pitch is that it stops trucks rolling to machines that turn out to
be fine. It follows that when its own diagnosis is wrong and a technician arrives to
find nothing to repair, that has to be expressible: the crew comes back, the component
goes back on the shelf unfitted, and the wasted journey is counted rather than filed
as a successful repair.

The failure this guards is quiet and expensive. Closing a no-fault visit through the
ordinary completion path books a *replacement* part into the depot (see
``store._replenish``, which is right for a component that was actually fitted). Do that
for a part that never left the van and the depot has invented a spare out of a wasted
trip, so stock drifts upward every time the model is wrong.
"""

from __future__ import annotations

import pytest

from app.agent import tools
from app.agent.tools import create_work_order
from app.models import FaultPrediction, utcnow
from app.nac.base import DeviceLocation
from app.store import store

PART = "HYD-PUMP-40L"


@pytest.fixture
def crew_stays_put(monkeypatch):
    async def _no_op(technicians):
        return "mock"

    monkeypatch.setattr(tools, "locate_crew", _no_op)


async def _dispatch():
    asset_id = sorted(store.assets)[0]
    inc = store.open_incident(asset_id, "test")
    return await create_work_order(
        inc.id,
        asset_id,
        FaultPrediction(
            asset_id=asset_id,
            mode="DEVICE_FAILURE",
            confidence=0.99,
            recommended_part=PART,
            component="hydraulic_pump",
        ),
        DeviceLocation(
            asset_id=asset_id,
            latitude=27.5,
            longitude=35.0,
            accuracy_m=25.0,
            as_of=utcnow(),
            source="mock",
        ),
    )


def _stock(wh_id: str, part: str) -> int:
    return store.warehouses[wh_id].stock.get(part, 0)


@pytest.mark.asyncio
async def test_the_part_goes_back_on_the_shelf_it_came_from(crew_stays_put):
    before = {w.id: _stock(w.id, PART) for w in store.warehouses.values()}
    wo = await _dispatch()
    assert wo.warehouse_id, "a component dispatch has to name the depot it drew from"
    assert _stock(wo.warehouse_id, PART) == before[wo.warehouse_id] - 1

    store.close_no_fault_found(wo)

    # Exactly back where it started. Not one more, which is what completing it would
    # have produced, and not one fewer.
    for wh_id, units in before.items():
        assert _stock(wh_id, PART) == units, f"{wh_id} drifted"


@pytest.mark.asyncio
async def test_a_completed_repair_still_consumes_and_resupplies(crew_stays_put):
    """The counterpart, so the two paths cannot quietly become the same one."""
    before = {w.id: _stock(w.id, PART) for w in store.warehouses.values()}
    wo = await _dispatch()
    store.complete_work_order(wo)

    # The component went into the machine and the depot books a replacement in, so the
    # shelf reads level. The distinction from the test above is not the arithmetic, it
    # is that one of these consumed a part and the other did not.
    assert _stock(wo.warehouse_id, PART) == before[wo.warehouse_id]
    assert wo.no_fault_found is False


@pytest.mark.asyncio
async def test_the_crew_and_the_machine_both_come_back(crew_stays_put):
    wo = await _dispatch()
    tech_id = wo.technician_id
    assert tech_id is not None
    assert not store.technicians[tech_id].available

    store.close_no_fault_found(wo)

    assert store.technicians[tech_id].available, "the technician has to return to the pool"
    assert store.assets[wo.asset_id].state == "healthy", (
        "nothing was wrong with the machine, so it goes back into service"
    )


@pytest.mark.asyncio
async def test_it_is_counted_rather_than_filed_as_a_repair(crew_stays_put):
    before = store.kpis().no_fault_found
    wo = await _dispatch()
    store.close_no_fault_found(wo)

    assert wo.no_fault_found is True
    assert wo.status == "completed"
    assert store.kpis().no_fault_found == before + 1


@pytest.mark.asyncio
async def test_closing_twice_does_not_double_count(crew_stays_put):
    """The operator's button is clickable twice and the timer can land on it too."""
    wo = await _dispatch()
    store.close_no_fault_found(wo)
    after_first = store.kpis().no_fault_found
    stock_after_first = _stock(wo.warehouse_id, PART)

    store.close_no_fault_found(wo)

    assert store.kpis().no_fault_found == after_first
    assert _stock(wo.warehouse_id, PART) == stock_after_first, "the part came back twice"
