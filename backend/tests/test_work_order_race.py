"""A dispatch is not one write, and the two gaps in the middle of it.

``create_work_order`` spends ~3.6s asking CAMARA Location Retrieval where each of the
six technicians is, and the agent then narrates one more trace step — 0.7s — after the
work order exists but before the asset is marked ``dispatched`` and the incident closed.
Two things could land in those gaps and leave the store incoherent:

* the operator cancelling or completing the job from the dashboard, which released the
  technician and put the machine back to ``healthy`` — and was then overwritten by the
  investigation, which marked the same asset ``dispatched`` and closed the incident
  against a work order that no longer existed. The freshness sweep skips ``dispatched``,
  so the machine was left permanently un-investigated with nothing on the way to it;
* a reset, which the tracer catches on its next step — but the work order has already
  been written by then, so a clean fleet came back with a dispatch on it.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, TypeVar

import pytest
from fastapi import HTTPException

from app.agent import run_investigation
from app.models import TraceStep, WorkOrder
from app.routes.workorders import complete_work_order as complete_route
from app.routes.workorders import delete_work_order as delete_route
from app.simulator import simulator
from app.store import store

T = TypeVar("T")


async def _wait_for(what: str, probe: Callable[[], T], timeout: float = 60.0) -> T:
    """Poll until the investigation reaches the point we want to interrupt."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = probe()
        if found:
            return found
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


def _start_hardware_investigation() -> tuple[str, str, asyncio.Task]:
    """A machine that goes dark with a real fault behind it, investigated in the background."""
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, "hardware")
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    task = asyncio.create_task(run_investigation(inc.id))
    return asset_id, inc.id, task


def _work_order_for(incident_id: str) -> WorkOrder | None:
    return next((w for w in store.work_orders.values() if w.incident_id == incident_id), None)


@pytest.mark.asyncio
async def test_cancelling_mid_dispatch_is_refused_and_the_machine_is_never_stranded():
    """The reported failure: cancel inside the settling window, asset stuck in ``dispatched``."""
    asset_id, incident_id, task = _start_hardware_investigation()
    try:
        wo = await _wait_for(
            "the work order to appear", lambda: _work_order_for(incident_id)
        )
        # We are inside the window: the card is on the dashboard and the agent has not
        # finished with the incident yet.
        assert store.incidents[incident_id].closed_at is None
        assert store.dispatch_in_flight(wo)

        with pytest.raises(HTTPException) as err:
            delete_route(wo.id)
        assert err.value.status_code == 409
        assert incident_id in str(err.value.detail)
    finally:
        await task

    # The investigation finished on its own terms, and everything agrees.
    assert store.assets[asset_id].state == "dispatched"
    assert wo.id in store.work_orders
    assert store.technicians[wo.technician_id].available is False
    # The state the guard exists to prevent: invisible to the detector, nobody en route.
    assert not (store.assets[asset_id].state == "dispatched" and _work_order_for(incident_id) is None)

    # And the operator's second click, a moment later, does what they asked.
    delete_route(wo.id)
    assert wo.id not in store.work_orders
    assert store.assets[asset_id].state == "healthy"
    assert store.technicians[wo.technician_id].available is True
    assert not simulator.is_silent(asset_id)


@pytest.mark.asyncio
async def test_completing_mid_dispatch_is_refused_too():
    """Signing the job off early strands the machine exactly as cancelling did."""
    asset_id, incident_id, task = _start_hardware_investigation()
    try:
        wo = await _wait_for(
            "the work order to appear", lambda: _work_order_for(incident_id)
        )
        with pytest.raises(HTTPException) as err:
            complete_route(wo.id)
        assert err.value.status_code == 409
        # Nothing was touched on the way to the refusal.
        assert wo.status != "completed"
        assert store.technicians[wo.technician_id].available is False
    finally:
        await task

    assert store.assets[asset_id].state == "dispatched"
    complete_route(wo.id)
    assert wo.status == "completed"
    assert store.assets[asset_id].state == "healthy"
    assert store.technicians[wo.technician_id].available is True


@pytest.mark.asyncio
async def test_reset_mid_dispatch_leaves_no_work_order_on_the_fresh_fleet():
    """Reset while the agent is on the phone to CAMARA about the crew.

    The last trace step before ``create_work_order`` is the crew-location one; after its
    0.7s pause the tracer checks the epoch and then hands off to a function with ~3.6s of
    network round trips and no epoch check in it at all. Resetting just past that check
    is the hole: the work order used to land on the brand-new fleet, and the tracer only
    noticed one step later — by which time the dispatch was already on the dashboard.
    """
    _, incident_id, task = _start_hardware_investigation()
    try:
        await _wait_for(
            "the crew-location step",
            lambda: any(
                s.args.get("subject") == "available crew"
                for s in store.trace.get(incident_id, [])
            ),
        )
        # Past that step's own post-pause epoch check, so the reset lands inside
        # create_work_order rather than being caught by the tracer before it.
        await asyncio.sleep(0.9)
        before = store.epoch
        store.reset()
    finally:
        await task

    assert store.epoch == before + 1
    assert store.work_orders == {}, "a dispatch for the old fleet survived the reset"
    assert store.kpis().dispatches_issued == 0
    assert incident_id not in store.incidents
    # The fresh fleet is genuinely untouched: nobody dispatched, nobody booked.
    assert all(a.state != "dispatched" for a in store.assets.values())
    assert all(t.available for t in store.technicians.values())


@pytest.mark.asyncio
async def test_a_work_order_for_a_previous_fleet_is_refused():
    """The guard itself, without the timing.

    A run that narrated its reasoning before the reset is a run reasoning about the old
    fleet, whatever it does afterwards.
    """
    asset_id = sorted(store.assets)[0]
    inc = store.open_incident(asset_id, "test")
    store.add_trace_step(
        TraceStep(incident_id=inc.id, step=1, thought="locating the crew")
    )
    store.reset()

    refused = WorkOrder(
        id=store.next_work_order_id(),
        incident_id=inc.id,
        asset_id=asset_id,
        fault_mode="DEVICE_FAILURE",
        confidence=0.9,
    )
    assert store.add_work_order(refused) is False
    assert store.work_orders == {}
    assert store.kpis().dispatches_issued == 0

    # An investigation that has narrated a step since the reset is reasoning about the
    # fleet in front of it, so its dispatch lands.
    fresh = store.open_incident(asset_id, "test")
    store.add_trace_step(
        TraceStep(incident_id=fresh.id, step=1, thought="locating the crew")
    )
    accepted = WorkOrder(
        id=store.next_work_order_id(), incident_id=fresh.id, asset_id=asset_id,
    )
    assert store.add_work_order(accepted) is True
    assert set(store.work_orders) == {accepted.id}
