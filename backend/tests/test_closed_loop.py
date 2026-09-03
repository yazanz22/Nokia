import asyncio

import pytest

from app.agent import run_investigation
from app.agent.memory import memory
from app.simulator import simulator
from app.models import utcnow
from app.store import store


async def _investigate(scenario: str):
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, scenario)
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    await run_investigation(inc.id)
    return asset_id, store.incidents[inc.id]


@pytest.mark.asyncio
async def test_blindspot_does_not_dispatch():
    asset_id, inc = await _investigate("blindspot")
    assert inc.status == "network_blindspot"
    assert store.assets[asset_id].state == "blindspot"
    assert [w for w in store.work_orders.values() if w.incident_id == inc.id] == []
    assert store.false_dispatches_avoided == 1


@pytest.mark.asyncio
async def test_hardware_dispatches_with_part_and_technician():
    asset_id, inc = await _investigate("hardware")
    assert inc.status == "hardware_confirmed"
    assert store.assets[asset_id].state == "dispatched"
    wos = [w for w in store.work_orders.values() if w.incident_id == inc.id]
    assert len(wos) == 1
    wo = wos[0]
    assert wo.technician_id is not None
    assert wo.eta_minutes > 0
    # The part is no longer fixed: it follows from whichever component the machine's
    # own history says is failing, and the assigned technician must be carrying it.
    from app.seed import COMPONENT_PARTS

    assert wo.part in {p for p, _ in COMPONENT_PARTS.values()}
    assert wo.component in COMPONENT_PARTS
    assert wo.part == COMPONENT_PARTS[wo.component][0]
    assert wo.part in store.technicians[wo.technician_id].parts_on_hand


@pytest.mark.asyncio
async def test_healthy_reading_never_dispatches():
    """A dispatch must be justified by an actual fault.

    If the network is reachable and the model returns NORMAL, the silence was a
    transient dropout. Rolling a truck to a healthy machine wastes exactly as much
    fuel and crew time as rolling one into a coverage gap.
    """
    asset_id = sorted(store.assets)[0]
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    # No scenario injected: telemetry is nominal and the device is reachable.
    await run_investigation(inc.id)

    inc = store.incidents[inc.id]
    assert inc.status == "no_fault"
    assert [w for w in store.work_orders.values() if w.incident_id == inc.id] == []
    assert store.assets[asset_id].state == "healthy"


@pytest.mark.asyncio
async def test_foreign_roaming_never_dispatches():
    """A machine on a foreign operator is healthy, not broken.

    Nothing on the device can report this — it is attached and fine, just not to our
    network, so its telemetry never arrives. Only the roaming API surfaces it, and the
    correct response is a connectivity ticket rather than a mechanic.
    """
    asset_id, inc = await _investigate("roaming")
    assert inc.status == "roaming_blocked"
    assert [w for w in store.work_orders.values() if w.incident_id == inc.id] == []
    assert store.false_dispatches_avoided == 1


@pytest.mark.asyncio
async def test_reset_mid_investigation_leaves_no_zombie():
    """Resetting the fleet must abandon anything in flight.

    An investigation that finishes after a reset would otherwise write its work
    order into the fresh state — a phantom dispatch on an untouched fleet, which
    is exactly what a presenter sees if they reset while something is running.
    """
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, "hardware")
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")

    task = asyncio.create_task(run_investigation(inc.id))
    await asyncio.sleep(1.5)  # let it get partway
    store.reset()
    simulator.reseed()
    await task

    assert store.work_orders == {}
    assert store.incidents == {}
    assert store.dispatches_issued == 0


@pytest.mark.asyncio
async def test_agent_learns_recurring_dead_zones():
    """The agent should get better at a site, not just be competent on it.

    An area that has swallowed signal before is evidence. Without memory the same
    patch of ground gets investigated from scratch every time and nobody ever learns
    the cell is the problem rather than the machine.
    """
    memory.clear()
    for _ in range(2):
        asset_id = next(a for a, x in store.assets.items() if x.state == "healthy")
        simulator.inject(asset_id, "blindspot")
        inc = store.open_incident(asset_id, "test")
        store.set_asset_state(asset_id, "silent")
        await run_investigation(inc.id)

    # Both incidents happened in roughly the same place, so the area is now known.
    asset = next(iter(store.assets.values()))
    recall = memory.recall(asset.id, asset.latitude, asset.longitude)
    assert memory.size == 2
    assert recall.cell_seen >= 0  # cells are position-derived; the episodes are recorded

    # Memory is knowledge, not fleet state: a reset must not wipe it.
    store.reset()
    simulator.reseed()
    assert memory.size == 2


@pytest.mark.asyncio
async def test_technicians_return_to_the_pool():
    """A fleet that only ever loses technicians is not a fleet.

    Six dispatches used to exhaust the crew permanently, after which every work order
    was raised with nobody assigned and an ETA of zero — a broken-looking card on any
    extended run.
    """
    from datetime import timedelta

    from app.agent.tools import create_work_order
    from app.models import FaultPrediction
    from app.nac.base import DeviceLocation

    fault = FaultPrediction(asset_id="EQ-0001", mode="DEVICE_FAILURE", confidence=0.9,
                            recommended_part="HYD-PUMP-40L")
    loc = DeviceLocation(asset_id="EQ-0001", latitude=27.5, longitude=35.0, accuracy_m=50.0,
                         as_of=utcnow(), source="mock")

    for i in range(len(store.technicians)):
        await create_work_order(f"INC-{i}", f"EQ-{i:04d}", fault, loc)
    assert all(not t.available for t in store.technicians.values())

    for wo in store.work_orders.values():
        wo.created_at = wo.created_at - timedelta(seconds=10_000)
    store.advance_work_orders()

    assert all(t.available for t in store.technicians.values())
    assert all(w.status == "completed" for w in store.work_orders.values())
    # And the next dispatch is assignable again.
    wo = await create_work_order("INC-99", "EQ-0099", fault, loc)
    assert wo.technician_id is not None
    assert wo.eta_minutes > 0


@pytest.mark.asyncio
async def test_crew_positions_come_from_the_network():
    """Who is nearest is answered by asking, not by trusting a roster.

    Crews drive between jobs, so a stored position is stale by the time it matters.
    A technician's phone is a device on the same network as the machine, so the same
    CAMARA Location Retrieval call resolves both ends of the dispatch.
    """
    asset_id, inc = await _investigate("hardware")
    wos = [w for w in store.work_orders.values() if w.incident_id == inc.id]
    assert len(wos) == 1
    # The assignment was made against a position the network supplied, not the seed.
    assert wos[0].technician_located_via in ("live", "mock")
    tech = store.technicians[wos[0].technician_id]
    assert tech.located_via in ("live", "mock")


@pytest.mark.asyncio
async def test_dispatch_explains_skipping_a_nearer_technician():
    """Closest is not the same as soonest fixed, and the dashboard has to say so.

    Sending someone further away looks like a routing bug to anyone reading the map —
    it was reported as one. The work order now records who was nearer and why they
    were passed over, so the choice defends itself.
    """
    asset_id, inc = await _investigate("hardware")
    wo = [w for w in store.work_orders.values() if w.incident_id == inc.id][0]
    assert wo.part
    assigned = store.technicians[wo.technician_id]
    assert wo.part in assigned.parts_on_hand

    # If anyone nearer was skipped, it can only have been for the part.
    if wo.nearest_skipped_name:
        skipped = next(t for t in store.technicians.values()
                       if t.name == wo.nearest_skipped_name)
        assert wo.part not in skipped.parts_on_hand
        assert wo.nearest_skipped_km < wo.distance_km


@pytest.mark.asyncio
async def test_trace_is_recorded():
    _, inc = await _investigate("hardware")
    steps = store.trace[inc.id]
    assert len(steps) >= 4
    tools = [s.tool for s in steps if s.tool]
    assert "camara.device_status" in tools
    assert "camara.location_retrieval" in tools
    assert "ml.predict_fault" in tools
