"""A SIM attached for SMS only is a connectivity cause, not a cleared network.

CAMARA Device Reachability reports how a device is attached: with a data session, or
for SMS only. Telemetry travels over data. So when a silent machine's SIM is attached
SMS-only, the network has already explained the silence — the modem is powered and
registered, it simply has no bearer to send on.

The code used to read ``connected`` ("data or SMS") everywhere that really meant
"could telemetry flow", and three things followed from it. The silence diagnosis said
connectivity was ruled out and routed toward a dispatch. The fault model was told the
device was reachable, so a network outage was not a verdict it could reach. And the
automated re-check put an SMS-only machine back in service, to go quiet again. The
mock never returns SMS-only, so none of this could appear in a demo; it happened only
against the live operator. These tests pin all three, and on both agents, because
divergence between the two agents is where this repo's bugs have lived.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.agent import agent as agent_mod
from app.agent import rule_agent as rule_mod
from app.agent import run_investigation, tools
from app.agent.agent import Deps, _build_agent
from app.agent.tools import assess_silence, clear_rechecks
from app.agent.trace import Tracer
from app.anomaly.detector import detector
from app.nac.base import Reachability
from app.nac.nokia import parse_reachability_status
from app.store import store


def _reach(status: str, **kw) -> Reachability:
    base = dict(
        asset_id="EQ-0001",
        status=status,
        roaming=False,
        country="SA",
        as_of=datetime.now(timezone.utc),
        source="live",
    )
    base.update(kw)
    return Reachability(**base)


def _work_orders_for(incident_id: str) -> list:
    return [w for w in store.work_orders.values() if w.incident_id == incident_id]


@pytest.fixture(autouse=True)
def clean_rechecks():
    """A no-dispatch outcome schedules a re-check. Nothing carried in or out of here."""
    clear_rechecks()
    detector._rechecking.clear()
    detector._agent_tasks.clear()
    yield
    clear_rechecks()
    detector._rechecking.clear()
    detector._agent_tasks.clear()


@pytest.fixture
def no_model_requests():
    with models.override_allow_model_requests(False):
        yield


# ── what the status means ────────────────────────────────────────────────────


def test_sms_only_is_attached_but_cannot_carry_telemetry():
    sms, data = _reach("CONNECTED_SMS"), _reach("CONNECTED_DATA")
    assert sms.connected and not sms.data_connected
    assert data.connected and data.data_connected
    for status in ("NOT_CONNECTED", "UNKNOWN"):
        r = _reach(status)
        assert not r.connected and not r.data_connected


# ── the silence diagnosis ────────────────────────────────────────────────────


def test_sms_only_on_our_network_sends_nobody():
    v = assess_silence(_reach("CONNECTED_SMS"))
    assert v.dispatch is False
    # The category both agents and the re-check already route to "nobody sent".
    assert v.category == "coverage_gap"
    assert "SMS" in v.explanation


def test_sms_only_is_not_overruled_by_a_strong_signal():
    """A strong cell with no neighbour failures reopens the hardware branch for a device
    that is unreachable. SMS-only is not unreachable: there is simply no data session, so
    telemetry still cannot flow and the signal changes nothing."""
    v = assess_silence(_reach("CONNECTED_SMS", signal_strength_dbm=-55.0, neighbor_fail_count=0))
    assert v.dispatch is False
    assert v.category == "coverage_gap"


def test_sms_only_while_roaming_abroad_is_still_a_roaming_ticket():
    """The Nokia sandbox SIM is exactly this: SMS-only, roaming, HU. Roaming is checked
    first, and the more specific story should keep winning."""
    v = assess_silence(_reach("CONNECTED_SMS", roaming=True, country="HU"))
    assert v.dispatch is False
    assert v.category == "roaming_out"


def test_a_data_session_on_our_network_still_goes_to_the_fault_model():
    """Unchanged: attached with data and not reporting is a question about the machine."""
    v = assess_silence(_reach("CONNECTED_DATA"))
    assert v.dispatch is True
    assert v.category == "inconclusive"


def test_an_operator_reply_without_a_connectivity_list_sends_nobody():
    """The parser reads a bare ``reachable: true`` as SMS-only — conservative about
    reachability. This pins that it is now conservative about dispatch as well."""
    status = parse_reachability_status({"reachable": True})
    assert status == "CONNECTED_SMS"
    assert assess_silence(_reach(status)).dispatch is False


# ── the fault model's input ──────────────────────────────────────────────────


def test_the_fault_model_is_told_an_sms_only_device_cannot_report(monkeypatch):
    """The model only reaches NETWORK_OUTAGE for a device it is told is unreachable, so
    handing it ``reachable=True`` for SMS-only took the network verdict off the table."""
    seen = []

    def capture(asset_id, sample):
        seen.append(sample)
        return None

    monkeypatch.setattr(tools.fault_model, "predict", capture)
    asset_id = sorted(store.assets)[0]
    tools.predict_fault(asset_id, _reach("CONNECTED_SMS", asset_id=asset_id))
    tools.predict_fault(asset_id, _reach("CONNECTED_DATA", asset_id=asset_id))

    assert [s.reachable for s in seen] == [False, True]


# ── both agents, end to end ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rule_agent_sends_nobody_to_an_sms_only_machine(monkeypatch):
    asset_id = sorted(store.assets)[0]
    reach = _reach("CONNECTED_SMS", asset_id=asset_id)

    async def fixed_status(_asset_id: str) -> Reachability:
        return reach

    monkeypatch.setattr(rule_mod, "check_device_status", fixed_status)
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")

    await run_investigation(inc.id)

    assert store.incidents[inc.id].status == "network_blindspot"
    assert _work_orders_for(inc.id) == []


@pytest.mark.asyncio
async def test_llm_agent_cannot_dispatch_to_an_sms_only_machine(monkeypatch, no_model_requests):
    """Scripted straight to ``dispatch_technician`` without assessing the network first —
    the route an LLM actually took in testing. The guard has to recompute the verdict
    itself, so this is the path that proves the fix holds for the LLM agent too."""
    asset_id = sorted(store.assets)[1]
    reach = _reach("CONNECTED_SMS", asset_id=asset_id)

    async def fixed_status(_asset_id: str) -> Reachability:
        return reach

    monkeypatch.setattr(agent_mod, "check_device_status", fixed_status)
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

    assert store.incidents[inc.id].status == "network_blindspot"
    assert _work_orders_for(inc.id) == []
    assert deps.terminal == "blindspot"
