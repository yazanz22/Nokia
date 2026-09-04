"""An investigation that has already dispatched must never be run a second time.

The agent's terminal tools mutate the store from inside the Pydantic AI run — work
order created, technician claimed, incident closed — and Pydantic AI then makes one
more model call to write its closing text. When *that* call fails (a Groq 429 is the
common case, and the retry loop exists precisely for it) the exception arrives after
the dispatch has already landed. Re-running from the top issues a second work order,
takes a second technician off the board, and counts `dispatches_issued` and the
triage-duration sample twice — while `store.trace[incident_id] = []` wipes the only
evidence, so the operator sees one tidy investigation over a doubled fleet.
"""

import pytest

from app.agent import run_investigation
from app.agent.rule_agent import run_rule_investigation
from app.config import get_settings
from app.simulator import simulator
from app.store import store


def _open_hardware_incident():
    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, "hardware")
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")
    return asset_id, inc


def _snapshot():
    return {
        "work_orders": len(store.work_orders),
        "dispatches": store.dispatches_issued,
        "triage_samples": len(store._triage_durations),
        "busy_technicians": sum(1 for t in store.technicians.values() if not t.available),
    }


@pytest.mark.asyncio
async def test_closed_incident_is_not_investigated_again():
    """The plain re-entry: a resolved incident handed back to the agent is a no-op."""
    _asset_id, inc = _open_hardware_incident()
    await run_investigation(inc.id)
    assert store.incidents[inc.id].closed_at is not None
    before = _snapshot()
    trace_before = list(store.trace[inc.id])

    await run_investigation(inc.id)

    assert _snapshot() == before
    # The trace of the run that actually dispatched has to survive too — resetting it
    # is what made the double-dispatch invisible in the first place.
    assert store.trace[inc.id] == trace_before


@pytest.mark.asyncio
async def test_rate_limit_after_dispatch_does_not_dispatch_twice(monkeypatch):
    """The 429 retry path: the model call that fails is the one *after* the dispatch."""
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_mode", "llm")

    calls = []

    async def fake_llm(incident_id: str) -> None:
        calls.append(incident_id)
        # First pass does the real work — work order, technician, incident closed —
        # then dies the way Pydantic AI dies when its closing model call is throttled.
        if len(calls) == 1:
            await run_rule_investigation(incident_id)
            raise RuntimeError("rate_limit_exceeded: please try again in 1.0s")

    import app.agent.agent as llm_mod

    monkeypatch.setattr(llm_mod, "run_llm_investigation", fake_llm)

    _asset_id, inc = _open_hardware_incident()
    await run_investigation(inc.id)

    assert calls == [inc.id], "the investigation was re-run after it had already closed"
    assert store.incidents[inc.id].status == "hardware_confirmed"
    assert len([w for w in store.work_orders.values() if w.incident_id == inc.id]) == 1
    assert store.dispatches_issued == 1
    assert len(store._triage_durations) == 1


@pytest.mark.asyncio
async def test_rule_fallback_after_dispatch_does_not_dispatch_twice(monkeypatch):
    """The fallback path: a non-429 failure after the dispatch must not re-run either."""
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_mode", "llm")

    calls = []

    async def fake_llm(incident_id: str) -> None:
        calls.append(incident_id)
        await run_rule_investigation(incident_id)
        # `run_llm_investigation` raises exactly this when the model narrates the
        # terminal tool instead of invoking it — but it can also be reached after a
        # genuine terminal call, and then the fallback would dispatch all over again.
        raise RuntimeError("no terminal action")

    import app.agent.agent as llm_mod

    monkeypatch.setattr(llm_mod, "run_llm_investigation", fake_llm)

    _asset_id, inc = _open_hardware_incident()
    await run_investigation(inc.id)

    assert calls == [inc.id]
    assert len([w for w in store.work_orders.values() if w.incident_id == inc.id]) == 1
    assert store.dispatches_issued == 1
