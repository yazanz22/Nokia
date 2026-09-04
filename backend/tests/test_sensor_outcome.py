"""A failed reporting sensor is its own outcome, not a hardware breakdown.

Both agents used to fall through the same terminal close for anything the model did
not call NORMAL or NETWORK_OUTAGE, so a `SENSOR_FAILURE` — a broken telemetry sensor
on a machine that is otherwise fine, fixed with a cheap `TELEMETRY-SENSOR-KIT` — was
recorded as `hardware_confirmed` and rendered on the dashboard as "hardware ·
dispatched", identically to a breakdown needing a mechanic and a heavy component.

The product's claim is that it *grades* the response to what actually broke: three
outcomes send nobody, one sends a kit, one sends a mechanic. If the two dispatching
outcomes are indistinguishable in the incident record, the fifth outcome does not
exist as far as anyone reading the record is concerned. These tests pin it in place —
including the parity between the two agents, which is where this repo's bugs live.
"""

from __future__ import annotations

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.agent import run_investigation
from app.agent import agent as agent_mod
from app.agent.agent import Deps, _build_agent
from app.agent.trace import Tracer
from app.models import FaultPrediction, utcnow
from app.nac.base import Reachability
from app.seed import PARTS_CATALOGUE
from app.simulator import simulator
from app.store import store

SENSOR_KIT = PARTS_CATALOGUE["SENSOR_FAILURE"][0]


def _work_orders_for(incident_id: str) -> list:
    return [w for w in store.work_orders.values() if w.incident_id == incident_id]


async def _investigate(scenario: str):
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, scenario)
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    await run_investigation(inc.id)
    return asset_id, store.incidents[inc.id]


# ── the rule agent (what the demo actually runs, and the LLM fallback) ───────


@pytest.mark.asyncio
async def test_sensor_fault_closes_as_sensor_confirmed_and_still_dispatches():
    """Somebody still goes — with a kit, not a mechanic, and the record says so."""
    asset_id, inc = await _investigate("sensor")

    assert inc.status == "sensor_confirmed"
    assert inc.closed_at is not None
    assert store.assets[asset_id].state == "dispatched"

    wos = _work_orders_for(inc.id)
    assert len(wos) == 1
    wo = wos[0]
    assert wo.part == SENSOR_KIT
    assert wo.fault_mode == "SENSOR_FAILURE"
    # The assigned technician has to actually be carrying it, same as any dispatch.
    assert wo.technician_id is not None
    assert SENSOR_KIT in store.technicians[wo.technician_id].parts_on_hand


@pytest.mark.asyncio
async def test_the_resolution_says_the_machine_is_fine():
    """The text an operator reads must not call this a hardware fault."""
    _asset_id, inc = await _investigate("sensor")

    assert "Hardware fault confirmed" not in inc.resolution
    assert "sensor" in inc.resolution.lower()
    assert SENSOR_KIT in inc.resolution


@pytest.mark.asyncio
async def test_a_real_breakdown_is_still_hardware_confirmed():
    """The other half of the distinction: splitting the statuses must not blur them."""
    _asset_id, inc = await _investigate("hardware")

    assert inc.status == "hardware_confirmed"
    assert _work_orders_for(inc.id)[0].part != SENSOR_KIT


# ── the LLM agent, driven by a scripted model ────────────────────────────────
# Divergence between the two agents has been a recurring bug class here, so the
# distinction is asserted on both rather than on whichever one happens to be wired
# up. No network call: Pydantic AI's own FunctionModel plays the model's part.


@pytest.fixture
def no_model_requests():
    with models.override_allow_model_requests(False):
        yield


def _sensor_prediction(asset_id: str) -> FaultPrediction:
    return FaultPrediction(
        asset_id=asset_id,
        mode="SENSOR_FAILURE",
        confidence=0.91,
        probabilities={"SENSOR_FAILURE": 0.91, "NORMAL": 0.05},
        recommended_part=SENSOR_KIT,
        rationale="Telemetry age above spec while every physical channel reads nominal.",
    )


@pytest.mark.asyncio
async def test_llm_agent_records_a_sensor_fault_the_same_way(monkeypatch, no_model_requests):
    """Same status, same part, same story as the rule agent."""
    asset_id = sorted(store.assets)[0]

    # Stated outright rather than drawn from the mock's random dataset row: the point
    # here is the terminal close, and a lottery for the network verdict would make
    # this test drift off the branch it exists to cover. Unreachable with a strong
    # cell and no neighbour failures is the "network is fine, the machine went quiet"
    # verdict, which is the only one that reaches the dispatch path.
    reach = Reachability(
        asset_id=asset_id, status="NOT_CONNECTED", signal_strength_dbm=-58.0,
        neighbor_fail_count=0, roaming=False, country="SA", source="mock", as_of=utcnow(),
    )

    async def fixed_status(_asset_id: str) -> Reachability:
        return reach

    monkeypatch.setattr(agent_mod, "check_device_status", fixed_status)
    monkeypatch.setattr(
        agent_mod, "predict_fault", lambda aid, _reach=None: _sensor_prediction(aid)
    )

    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")

    calls = [("dispatch_technician", {})]

    def fn(messages, info) -> ModelResponse:
        if calls:
            name, args = calls.pop(0)
            return ModelResponse(parts=[ToolCallPart(tool_name=name, args=args)])
        return ModelResponse(parts=[TextPart("done")])

    agent = _build_agent()
    deps = Deps(incident_id=inc.id, asset_id=asset_id, tracer=Tracer(inc.id))
    with agent.override(model=FunctionModel(fn)):
        await agent.run("Investigate and take the correct terminal action.", deps=deps)

    closed = store.incidents[inc.id]
    assert closed.status == "sensor_confirmed"
    assert "Hardware fault confirmed" not in closed.resolution
    assert store.assets[asset_id].state == "dispatched"

    wos = _work_orders_for(inc.id)
    assert len(wos) == 1
    assert wos[0].part == SENSOR_KIT
    # Still exactly one terminal outcome, claimed through the same mechanism as the
    # other four — a sensor dispatch must not open a second way to close an incident.
    assert deps.terminal == "sensor dispatch"
