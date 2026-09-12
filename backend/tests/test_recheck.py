"""The scheduled re-check has to be a real thing that happens.

``schedule_recheck`` used to return ``utcnow() + 15 minutes`` and do nothing with it.
Every surface said otherwise: the trace step read "re-check queued; operator notified",
the incident resolution read "Re-check at 14:32 UTC", and the asset was parked in
``blindspot`` — the one state the freshness sweep skips forever. Nothing ever came back
for the machine, so the product's headline blind-spot outcome ("we don't send anyone, we
schedule an automated re-check") was true only up to the comma.

These tests hold the two halves together: that scheduling registers something the
detector can find, and that the detector acts on it — puts a recovered machine back on
the air, waits again when the dead zone is still dead, and never turns either into an
incident storm.
"""

import asyncio
from datetime import timedelta

import pytest

from app.agent import run_investigation
from app.agent.tools import (
    clear_rechecks,
    due_rechecks,
    pending_recheck,
    schedule_recheck,
)
from app.anomaly.detector import MAX_RECHECK_ATTEMPTS, detector
from app.config import get_settings
from app.models import utcnow
from app.nac.base import Reachability
from app.simulator import simulator
from app.store import store


@pytest.fixture(autouse=True)
def clean_rechecks():
    """No promises carried in or out.

    Deliberately not ``detector.reset()``: that restarts the sweep loop, and a
    background task racing these tests would re-check assets out from under them.
    """
    clear_rechecks()
    detector._rechecking.clear()
    detector._agent_tasks.clear()
    yield
    clear_rechecks()
    detector._rechecking.clear()
    detector._agent_tasks.clear()


async def _blindspot() -> tuple[str, str]:
    """Drive a real investigation to the coverage-gap outcome. Returns (asset, incident)."""
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, "blindspot")
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    await run_investigation(inc.id)
    assert store.incidents[inc.id].status == "network_blindspot"
    return asset_id, inc.id


def _make_due(asset_id: str) -> None:
    pending = pending_recheck(asset_id)
    assert pending is not None
    pending.due_at = utcnow() - timedelta(seconds=1)


async def _run_due_rechecks() -> None:
    """One sweep, then wait for the CAMARA calls it spawned."""
    detector._sweep_rechecks()
    tasks = list(detector._agent_tasks)
    detector._agent_tasks.clear()
    if tasks:
        await asyncio.gather(*tasks)


# ── scheduling ───────────────────────────────────────────────────────────────


def test_scheduling_registers_something_findable():
    """The regression itself: the return value used to be the only effect."""
    at = schedule_recheck("EQ-0001", minutes=15)
    pending = pending_recheck("EQ-0001")
    assert pending is not None
    # The time printed in the trace and the time the detector will act on are the
    # same time, or the text is lying again — just more convincingly.
    assert pending.due_at == at


def test_interval_is_demo_length_and_configurable(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "recheck_after_seconds", 10)
    before = utcnow()
    at = schedule_recheck("EQ-0001", minutes=15)
    assert timedelta(seconds=9) <= at - before <= timedelta(seconds=12)
    # A roaming ticket is scheduled at 30 nominal minutes and must still wait longer
    # than a blind spot's 15 — compressing the clock must not flatten the two.
    roaming_at = schedule_recheck("EQ-0002", minutes=30)
    assert roaming_at - before > at - before


def test_a_reset_voids_outstanding_rechecks():
    """The smoke script and the test fixtures reset the store without the detector."""
    schedule_recheck("EQ-0001", minutes=15)
    _make_due("EQ-0001")
    store.reset()
    simulator.reseed()
    assert due_rechecks() == []


@pytest.mark.asyncio
async def test_a_blindspot_investigation_queues_a_real_recheck():
    asset_id, _ = await _blindspot()
    assert store.assets[asset_id].state == "blindspot"
    assert pending_recheck(asset_id) is not None


# ── the detector acting on it ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recheck_puts_a_recovered_machine_back_on_the_air():
    asset_id, incident_id = await _blindspot()
    # The machine drove out of the dead zone: coverage is back, so CAMARA Device
    # Status answers for it again.
    simulator.clear(asset_id)

    _make_due(asset_id)
    steps_before = len(store.trace[incident_id])
    await _run_due_rechecks()

    assert store.assets[asset_id].state == "healthy"
    # The half that two earlier bugs in this codebase got wrong: healthy but still
    # muted means last_seen never advances and the detector re-opens the same
    # incident thirty seconds later, forever.
    assert not simulator.is_silent(asset_id)
    assert simulator.pending_label(asset_id) is None
    assert pending_recheck(asset_id) is None
    # And it is visible that it happened, on the incident that promised it.
    assert len(store.trace[incident_id]) > steps_before


@pytest.mark.asyncio
async def test_recheck_waits_again_when_the_dead_zone_is_still_dead():
    asset_id, incident_id = await _blindspot()
    _make_due(asset_id)
    steps_before = len(store.trace[incident_id])
    await _run_due_rechecks()

    pending = pending_recheck(asset_id)
    assert pending is not None
    assert pending.attempts == 1
    assert pending.due_at > utcnow()
    # Nothing about the machine changed, so nothing about its state should have.
    assert store.assets[asset_id].state == "blindspot"
    assert simulator.is_silent(asset_id)
    assert len(store.trace[incident_id]) > steps_before


@pytest.mark.asyncio
async def test_a_permanent_blindspot_does_not_become_an_incident_storm():
    """The scenario the demo opens with is injected permanently and never clears."""
    asset_id, _ = await _blindspot()
    incidents_before = len(store.incidents)
    work_orders_before = len(store.work_orders)

    for _ in range(3):
        _make_due(asset_id)
        await _run_due_rechecks()

    assert len(store.incidents) == incidents_before
    assert len(store.work_orders) == work_orders_before
    assert store.assets[asset_id].state == "blindspot"


@pytest.mark.asyncio
async def test_recheck_stands_down_after_the_attempt_cap():
    """A dead zone that outlasts every attempt is a coverage problem, not a poll."""
    asset_id, incident_id = await _blindspot()
    pending = pending_recheck(asset_id)
    assert pending is not None
    pending.attempts = MAX_RECHECK_ATTEMPTS - 1
    _make_due(asset_id)
    await _run_due_rechecks()

    assert pending_recheck(asset_id) is None
    assert store.assets[asset_id].state == "blindspot"
    assert "persistent dead zone" in store.trace[incident_id][-1].observation


@pytest.mark.asyncio
async def test_recheck_is_dropped_for_a_machine_already_back_in_service():
    """The no-fault branch resumes telemetry immediately; there is nothing to re-check."""
    asset_id, incident_id = await _blindspot()
    store.resume_telemetry(asset_id)

    _make_due(asset_id)
    steps_before = len(store.trace[incident_id])
    await _run_due_rechecks()

    assert pending_recheck(asset_id) is None
    assert store.assets[asset_id].state == "healthy"
    # Cancelled, not silently expired — the incident said a re-check was coming.
    assert len(store.trace[incident_id]) > steps_before


@pytest.mark.asyncio
async def test_a_roaming_device_is_not_treated_as_back():
    """Attached, but to somebody else's network — its telemetry still cannot reach us."""
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, "roaming")
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    await run_investigation(inc.id)
    assert store.incidents[inc.id].status == "roaming_blocked"

    _make_due(asset_id)
    await _run_due_rechecks()

    assert store.assets[asset_id].state == "blindspot"
    assert pending_recheck(asset_id) is not None


@pytest.mark.asyncio
async def test_an_sms_only_device_is_not_treated_as_back(monkeypatch):
    """Attached, but with no data session — its telemetry still cannot reach us.

    Counting SMS-only as back put a machine into service that could not report, which
    went quiet again and reopened the same incident. The mock never answers SMS-only,
    so this only happened against the live operator.
    """
    asset_id, incident_id = await _blindspot()

    async def sms_only(_asset_id: str) -> Reachability:
        return Reachability(
            asset_id=_asset_id, status="CONNECTED_SMS", roaming=False, country="SA",
            as_of=utcnow(), source="live",
        )

    # The detector imports the status call when it runs, so patch it where it lives.
    import app.agent.tools as tools_mod

    monkeypatch.setattr(tools_mod, "check_device_status", sms_only)
    _make_due(asset_id)
    await _run_due_rechecks()

    assert store.assets[asset_id].state == "blindspot"
    assert pending_recheck(asset_id) is not None
    last = str(store.trace[incident_id][-1].model_dump(mode="json"))
    assert "CONNECTED_SMS" in last
    # And it says what it saw, rather than calling an attached SIM unreachable.
    assert "SMS only" in last
