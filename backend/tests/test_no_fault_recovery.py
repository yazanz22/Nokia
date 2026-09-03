"""A machine judged healthy has to actually come back.

The no-fault branch is the quiet one: no work order, no dispatch, nothing on the
map. So when it left the simulator withholding telemetry, the only symptom was the
detector re-opening the same incident half a minute later, forever — an investigation
loop with no visible cause. Reachable in a normal demo, because the diagnostic model
confuses roughly half of all sensor faults with healthy readings by design.
"""

import pytest

from app.agent import run_investigation
from app.ml.client import fault_model
from app.models import FaultPrediction
from app.simulator import simulator
from app.store import store


@pytest.fixture
def model_finds_nothing(monkeypatch):
    """Force the diagnostic model to return NORMAL, whatever was injected."""
    monkeypatch.setattr(
        fault_model,
        "predict",
        lambda asset_id, sample: FaultPrediction(
            asset_id=asset_id, mode="NORMAL", confidence=0.91,
            rationale="all channels nominal", recommended_part="",
        ),
    )


async def _investigate(scenario: str):
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, scenario)
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    await run_investigation(inc.id)
    return asset_id, store.incidents[inc.id]


@pytest.mark.asyncio
async def test_no_fault_puts_the_machine_back_on_the_air(model_finds_nothing):
    asset_id, inc = await _investigate("sensor")

    assert inc.status == "no_fault"
    assert store.assets[asset_id].state == "healthy"
    # The actual regression: healthy but still muted means the detector fires again.
    assert not simulator.is_silent(asset_id)
    assert simulator.pending_label(asset_id) is None


@pytest.mark.asyncio
async def test_no_fault_does_not_dispatch(model_finds_nothing):
    _, inc = await _investigate("sensor")
    assert [w for w in store.work_orders.values() if w.incident_id == inc.id] == []
    assert store.false_dispatches_avoided == 1
