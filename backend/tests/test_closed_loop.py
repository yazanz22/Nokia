import asyncio

import pytest

from app.agent import run_investigation
from app.simulator import simulator
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
    assert wo.part == "HYD-PUMP-40L"
    assert wo.eta_minutes > 0


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
async def test_trace_is_recorded():
    _, inc = await _investigate("hardware")
    steps = store.trace[inc.id]
    assert len(steps) >= 4
    tools = [s.tool for s in steps if s.tool]
    assert "camara.device_status" in tools
    assert "camara.location_retrieval" in tools
    assert "ml.predict_fault" in tools
