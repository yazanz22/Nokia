"""A dispatch with nobody free must not be recorded as a dispatch.

The crew is six people and jobs auto-complete on a demo clock, so "every technician is
already out" is reachable in a long session or by a judge clicking twice too often.
What used to happen then: `create_work_order` left `tech = None`, the work order was
written as `status="created"` with an empty name and a zero ETA, both agents printed
"dispatched to  (ETA 0 min)", and the asset was parked in `dispatched` — a state the
anomaly sweep skips. A machine nobody was driving to was also a machine nobody was
watching, and it stayed dark until somebody hit Reset.

The honest outcome instead: the job is queued and says so, the incident closes as
`awaiting_crew`, the asset stays on the sweep, and the next investigation hands the
same queued job to the first technician who frees.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.agent import run_investigation
from app.agent.tools import create_work_order
from app.anomaly import detector
from app.config import get_settings
from app.models import FaultPrediction, utcnow
from app.nac.base import DeviceLocation
from app.simulator import simulator
from app.store import store


def _book_the_whole_crew() -> None:
    for tech in store.technicians.values():
        tech.available = False


async def _investigate(asset_id: str) -> str:
    """What the detector does, without the detector: go dark, open, investigate."""
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    await run_investigation(inc.id)
    return inc.id


def _go_dark(asset_id: str) -> None:
    """Backdate the heartbeat the way a real re-trigger would see it."""
    store.assets[asset_id].last_seen = utcnow() - timedelta(
        seconds=get_settings().silent_threshold_seconds + 5
    )


def _orders_for(asset_id: str) -> list:
    return [w for w in store.work_orders.values() if w.asset_id == asset_id]


@pytest.mark.asyncio
async def test_a_fully_booked_crew_queues_the_job_instead_of_faking_a_dispatch():
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, "hardware")
    _book_the_whole_crew()

    inc_id = await _investigate(asset_id)
    inc = store.incidents[inc_id]

    assert inc.status == "awaiting_crew", (
        f"a fault nobody was sent to closed as {inc.status!r} — the incident record has to "
        "distinguish 'diagnosed and queued' from 'diagnosed and dispatched'"
    )
    # The exact shape of the reported bug.
    assert "dispatched to  " not in inc.resolution
    assert "ETA 0 min" not in inc.resolution
    assert "queued" in inc.resolution.lower()

    orders = _orders_for(asset_id)
    assert len(orders) == 1, "one broken machine, one job"
    wo = orders[0]
    assert wo.status == "queued"
    assert wo.technician_id is None and wo.technician_name == ""
    assert wo.eta_minutes == 0 and wo.distance_km == 0.0
    # The diagnosis is still on the card — this is a real job waiting for a person,
    # not a placeholder.
    assert wo.part and wo.fault_mode

    # Nothing rolled, so nothing is counted as rolled.
    assert store.kpis().dispatches_issued == 0
    assert store.false_dispatches_avoided == 0, "declining to send is not the same as avoiding a wasted trip"


@pytest.mark.asyncio
async def test_the_queued_machine_stays_visible_to_the_anomaly_sweep(monkeypatch):
    """The half of the bug that hid the machine.

    `dispatched` and `silent` are both skipped by the freshness sweep, so parking a
    queued asset in either means it is never looked at again.
    """
    asset_id, control = sorted(store.assets)[:2]
    simulator.inject(asset_id, "hardware")
    _book_the_whole_crew()
    await _investigate(asset_id)

    assert store.assets[asset_id].state not in ("dispatched", "silent", "blindspot")

    # Ask the detector itself rather than hard-coding its skip list here.
    store.set_asset_state(control, "dispatched")
    triggered: list[str] = []
    monkeypatch.setattr(detector, "_trigger", lambda a, age: triggered.append(a))
    _go_dark(asset_id)
    detector._sweep(get_settings().silent_threshold_seconds)

    assert asset_id in triggered, (
        "a machine with a confirmed fault and nobody assigned dropped off the sweep — "
        "nobody is coming and nobody is watching"
    )
    assert control not in triggered, "control: a real dispatch is still skipped"


@pytest.mark.asyncio
async def test_the_queued_job_is_picked_up_when_a_technician_frees():
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, "hardware")
    _book_the_whole_crew()
    await _investigate(asset_id)
    queued = _orders_for(asset_id)[0]

    # A job finishes somewhere else on site; the sweep re-opens the machine it never
    # stopped watching.
    freed = next(iter(store.technicians.values()))
    freed.available = True
    _go_dark(asset_id)
    inc_id = await _investigate(asset_id)

    orders = _orders_for(asset_id)
    assert len(orders) == 1, (
        "the second investigation raised a duplicate job for the same machine instead of "
        "picking up the one already queued"
    )
    wo = orders[0]
    assert wo.id == queued.id, "the operator should watch one card change, not collect cards"
    assert wo.status == "assigned"
    assert wo.technician_id is not None
    assert wo.eta_minutes > 0
    assert store.incidents[inc_id].status in ("hardware_confirmed", "sensor_confirmed")
    assert store.assets[asset_id].state == "dispatched"
    # Counted once, at the point it became a real dispatch.
    assert store.kpis().dispatches_issued == 1


@pytest.mark.asyncio
async def test_create_work_order_queues_rather_than_naming_nobody():
    """The tool itself, without an agent around it."""
    _book_the_whole_crew()
    fault = FaultPrediction(
        asset_id="EQ-0001", mode="DEVICE_FAILURE", confidence=0.9,
        recommended_part="HYD-PUMP-40L",
    )
    loc = DeviceLocation(asset_id="EQ-0001", latitude=27.5, longitude=35.0,
                         accuracy_m=50.0, as_of=utcnow(), source="mock")

    # Incident ids the store never minted: `add_work_order` refuses an order whose
    # incident was opened in an earlier epoch, and "INC-0001" is a real id from an
    # earlier test's fleet.
    first = await create_work_order("INC-QUEUE-A", "EQ-0001", fault, loc)
    assert first.status == "queued"
    assert first.technician_id is None
    assert first.nearest_skipped_name == "", "nobody was passed over — everybody is out"

    # Asked again for the same machine: the waiting job is refreshed, not duplicated,
    # and its clock is pushed forward so `advance_work_orders` cannot quietly
    # "complete" a repair no one performed.
    before = first.created_at
    second = await create_work_order("INC-QUEUE-B", "EQ-0001", fault, loc)
    assert second.id == first.id
    assert second.status == "queued"
    assert second.created_at >= before
    assert len(store.work_orders) == 1
    assert store.kpis().dispatches_issued == 0
