"""Finishing a job has to actually end the scenario.

A completed repair that leaves the simulator withholding telemetry produces a machine
that is "healthy" but still silent, so the detector re-opens an incident on it seconds
later and the agent dispatches somebody all over again — forever, on an idle dashboard.
"""

import pytest

from app.agent import run_investigation
from app.simulator import simulator
from app.store import store


async def _dispatch_one():
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, "hardware")
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    await run_investigation(inc.id)
    wos = [w for w in store.work_orders.values() if w.incident_id == inc.id]
    assert len(wos) == 1
    return asset_id, wos[0]


@pytest.mark.asyncio
async def test_completing_a_job_restores_the_machine_and_frees_the_crew():
    asset_id, wo = await _dispatch_one()
    tech_id = wo.technician_id
    assert tech_id is not None
    assert store.technicians[tech_id].available is False

    store.complete_work_order(wo)

    assert wo.status == "completed"
    assert store.technicians[tech_id].available is True
    assert store.assets[asset_id].state == "healthy"
    # The repair is what ends the scenario — otherwise the heartbeat never returns.
    assert not simulator.is_silent(asset_id)
    assert simulator.pending_label(asset_id) is None


@pytest.mark.asyncio
async def test_completing_twice_is_a_no_op():
    _, wo = await _dispatch_one()
    store.complete_work_order(wo)
    freed = store.technicians[wo.technician_id].available
    store.complete_work_order(wo)
    assert wo.status == "completed"
    assert store.technicians[wo.technician_id].available is freed


@pytest.mark.asyncio
async def test_deleting_an_open_job_releases_everything():
    asset_id, wo = await _dispatch_one()
    tech_id = wo.technician_id

    store.delete_work_order(wo)

    assert wo.id not in store.work_orders
    assert store.technicians[tech_id].available is True
    assert store.assets[asset_id].state == "healthy"
    assert not simulator.is_silent(asset_id)


@pytest.mark.asyncio
async def test_auto_complete_uses_the_same_path():
    """The timer and the button must leave the fleet in the same state."""
    from app.config import get_settings

    asset_id, wo = await _dispatch_one()
    settings = get_settings()
    original = settings.work_order_complete_seconds
    settings.work_order_complete_seconds = 0
    try:
        store.advance_work_orders()
    finally:
        settings.work_order_complete_seconds = original

    assert wo.status == "completed"
    assert store.assets[asset_id].state == "healthy"
    assert not simulator.is_silent(asset_id)
