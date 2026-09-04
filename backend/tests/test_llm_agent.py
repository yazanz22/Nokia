"""The LLM agent, driven by a scripted model instead of Groq.

`conftest.py` pins the whole suite to `AGENT_MODE=rule`, but the deployed `.env` runs
`AGENT_MODE=llm` — so the agent that actually resolves incidents on stage was the one
piece of the system with no tests at all. These cover it without a network call, an API
key or a token of quota, using Pydantic AI's own `FunctionModel` (a local function that
plays the part of the model) and `Agent.override`.

What is deliberately *not* covered here: the real model's behaviour. A scripted model
proves the agent's guardrails hold whatever the model does, which is the property the
deck claims. It cannot prove that `gpt-oss-120b` picks sensible tools — only
`scripts/scenario_smoke.py` against the live endpoint can, and that costs quota.
"""

from __future__ import annotations

import contextlib

import pytest
from pydantic_ai import models
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel

from app.agent import _retry_after
from app.agent import agent as agent_mod
from app.agent.agent import Deps, _build_agent, run_llm_investigation
from app.agent.trace import Tracer
from app.models import utcnow
from app.nac.base import Reachability
from app.simulator import simulator
from app.store import store


@pytest.fixture(autouse=True)
def no_model_requests():
    """Fail loudly if anything in this file reaches for a real provider.

    The whole point of the file is that it never talks to Groq. Pydantic AI's own
    kill-switch makes that a hard guarantee rather than a claim in a docstring: any
    real model request raises instead of quietly spending quota.
    """
    with models.override_allow_model_requests(False):
        yield


def _reach(**kw) -> Reachability:
    """Network evidence, stated outright.

    The mock NaC client picks a random dataset row, so driving these guards through it
    would make the *verdict* a lottery — and a guard test whose input drifts is a guard
    test that stops testing the guard. Same helper shape as test_terminal_guards.py.
    """
    base = dict(
        asset_id="EQ-0001", status="NOT_CONNECTED", signal_strength_dbm=-58.0,
        neighbor_fail_count=0, roaming=False, country="SA", source="mock", as_of=utcnow(),
    )
    base.update(kw)
    return Reachability(**base)


HARDWARE = dict(status="NOT_CONNECTED", signal_strength_dbm=-58.0, neighbor_fail_count=0)
COVERAGE_GAP = dict(status="NOT_CONNECTED", signal_strength_dbm=-127.0, neighbor_fail_count=12)
ROAMING = dict(status="CONNECTED_DATA", signal_strength_dbm=-71.0, neighbor_fail_count=0,
               roaming=True, country="JO")


def _script(*calls: tuple[str, dict]) -> FunctionModel:
    """A model that makes exactly these tool calls, in order, then answers in text.

    This is how the guards get driven the way they actually fail in production: the
    model skipping `assess_coverage` and jumping straight to a terminal tool.
    """
    remaining = list(calls)

    def fn(messages, info) -> ModelResponse:
        if remaining:
            name, args = remaining.pop(0)
            return ModelResponse(parts=[ToolCallPart(tool_name=name, args=args)])
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(fn)


def _tool_returns(result) -> dict[str, str]:
    """Every tool's return value, by tool name — what the model was told back."""
    out: dict[str, str] = {}
    for message in result.all_messages():
        for part in message.parts:
            if isinstance(part, ToolReturnPart):
                out[part.tool_name] = str(part.content)
    return out


async def _drive(monkeypatch, reach: Reachability, *calls: tuple[str, dict]):
    """Open a real incident and let a scripted model loose on it."""
    async def fixed_status(asset_id: str) -> Reachability:
        return reach

    monkeypatch.setattr(agent_mod, "check_device_status", fixed_status)

    asset_id = sorted(store.assets)[0]
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")

    agent = _build_agent()
    deps = Deps(incident_id=inc.id, asset_id=asset_id, tracer=Tracer(inc.id))
    with agent.override(model=_script(*calls)):
        result = await agent.run("Investigate and take the correct terminal action.", deps=deps)
    return asset_id, store.incidents[inc.id], deps, _tool_returns(result)


def _work_orders_for(incident_id: str) -> list:
    return [w for w in store.work_orders.values() if w.incident_id == incident_id]


# ── The three terminal guards ────────────────────────────────────────────────
# Each terminal tool re-derives the verdict from the network evidence rather than
# trusting that the model called the assessment tool first. test_terminal_guards.py
# asserts the *conditions* those guards check; these assert the guards actually fire
# when a model walks straight past the assessment and into the terminal call.


async def test_dispatch_refuses_a_device_that_is_merely_roaming(monkeypatch):
    """A machine on a foreign operator is healthy — sending a mechanic is the bug.

    This is the regression the guard was written for: the model went from device
    status straight to `dispatch_technician`, `deps.verdict` was never populated, and
    an earlier guard that read only `deps.verdict` silently did not fire.
    """
    asset_id, inc, deps, returns = await _drive(
        monkeypatch, _reach(**ROAMING), ("dispatch_technician", {}),
    )

    assert _work_orders_for(inc.id) == []
    assert inc.status == "roaming_blocked"
    assert store.assets[asset_id].state == "blindspot"
    assert store.dispatches_issued == 0
    assert store.false_dispatches_avoided == 1
    assert deps.terminal == "roaming"


async def test_dispatch_refuses_a_coverage_gap(monkeypatch):
    """The one outcome this product exists to stop a truck rolling for.

    A blind-spot frame is not NORMAL and carries no part, so before this guard existed
    it passed every downstream check and a technician was sent into a dead zone
    carrying nothing.
    """
    asset_id, inc, deps, returns = await _drive(
        monkeypatch, _reach(**COVERAGE_GAP), ("dispatch_technician", {}),
    )

    assert _work_orders_for(inc.id) == []
    assert inc.status == "network_blindspot"
    assert store.assets[asset_id].state == "blindspot"
    assert store.dispatches_issued == 0
    assert store.false_dispatches_avoided == 1
    assert deps.terminal == "blindspot"


async def test_blindspot_refuses_when_the_evidence_shows_a_fault(monkeypatch):
    """Closing a real breakdown as a coverage gap is the silent false negative.

    Nobody is ever dispatched and the dashboard looks like the product working. The
    tool has to refuse and say why, leaving the incident open for the model to retry.
    """
    asset_id, inc, deps, returns = await _drive(
        monkeypatch, _reach(**HARDWARE),
        ("resolve_as_blindspot", {"reason": "I think this is a dead zone"}),
    )

    assert returns["resolve_as_blindspot"].startswith("refused:")
    assert "does not show a coverage gap" in returns["resolve_as_blindspot"]
    assert inc.closed_at is None
    assert inc.status not in ("network_blindspot", "roaming_blocked")
    assert store.false_dispatches_avoided == 0
    assert deps.terminal is None


async def test_roaming_refuses_a_device_on_the_home_network(monkeypatch):
    """Same failure mode as the blind-spot guard, different label on the ticket.

    A connectivity ticket raised against a genuinely broken machine strands it in the
    desert — the mirror image of a wasted dispatch, and the more expensive mistake.
    """
    asset_id, inc, deps, returns = await _drive(
        monkeypatch, _reach(**HARDWARE), ("resolve_as_roaming", {}),
    )

    assert returns["resolve_as_roaming"].startswith("refused:")
    assert "not attached to a foreign network" in returns["resolve_as_roaming"]
    assert inc.closed_at is None
    assert store.false_dispatches_avoided == 0
    assert deps.terminal is None


async def test_blindspot_hands_a_roaming_device_to_the_roaming_tool(monkeypatch):
    """Refusing is not the only correct answer — the right action still gets taken.

    Roaming evidence handed to `resolve_as_blindspot` is not a coverage gap, but it is
    also not a dispatch. The tool re-routes rather than bouncing it back to the model,
    so the incident closes with the correct status on the first attempt.
    """
    asset_id, inc, deps, returns = await _drive(
        monkeypatch, _reach(**ROAMING),
        ("resolve_as_blindspot", {"reason": "signal looked weak"}),
    )

    assert inc.status == "roaming_blocked"
    assert _work_orders_for(inc.id) == []
    assert deps.terminal == "roaming"


async def test_guards_hold_without_the_model_ever_checking_device_status(monkeypatch):
    """The terminal tools fetch the evidence themselves if the model never did.

    Every guard above depends on `_reach` being populated. A model that calls nothing
    at all before dispatching would leave it `None` — the tool has to go and get it
    rather than fall through the guard on missing data.
    """
    asset_id, inc, deps, returns = await _drive(
        monkeypatch, _reach(**COVERAGE_GAP), ("dispatch_technician", {}),
    )

    assert deps._reach is not None  # the tool fetched it
    assert _work_orders_for(inc.id) == []
    assert inc.status == "network_blindspot"


# ── The re-ask path and the rule fallback ────────────────────────────────────


@contextlib.contextmanager
def _llm_agent_using(monkeypatch, model: FunctionModel):
    """Make `run_llm_investigation` build its agent against `model` instead of Groq.

    The agent is constructed inside `run_llm_investigation`, so there is no instance to
    override from out here — patch the builder and override the agent it hands back.
    """
    real_build = agent_mod._build_agent
    with contextlib.ExitStack() as stack:
        def build():
            agent = real_build()
            stack.enter_context(agent.override(model=model))
            return agent

        monkeypatch.setattr(agent_mod, "_build_agent", build)
        yield


def _already_returned(messages, tool_name: str) -> bool:
    """Has this tool already run in this conversation?

    Without this the scripted model re-issues the same terminal call every turn and the
    run spins until Pydantic AI's request limit trips.
    """
    return any(
        isinstance(part, ToolReturnPart) and part.tool_name == tool_name
        for message in messages
        for part in message.parts
    )


def _was_re_asked(messages) -> bool:
    """Is this the second run — the explicit 'you have not finished' prompt?"""
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, UserPromptPart) and "You have not finished" in str(part.content):
                return True
    return False


async def test_a_described_tool_call_is_re_asked_and_recovered(monkeypatch):
    """Open-weight models describe the final call instead of making it.

    The diagnosis is already done at that point; giving up would throw the whole
    investigation away and hand a solved incident to the rule agent. The agent asks
    once more, explicitly, and the run completes.
    """
    turns: list[bool] = []

    def fn(messages, info) -> ModelResponse:
        re_asked = _was_re_asked(messages)
        turns.append(re_asked)
        if not re_asked:
            # Exactly the failure mode: the tool call written out as text.
            return ModelResponse(parts=[TextPart(
                'resolve_as_blindspot({"reason": "weak signal, neighbour failures"})'
            )])
        if _already_returned(messages, "resolve_as_blindspot"):
            return ModelResponse(parts=[TextPart("blind spot logged")])
        return ModelResponse(parts=[
            ToolCallPart(tool_name="resolve_as_blindspot",
                         args={"reason": "weak signal, neighbour failures"}),
        ])

    async def fixed_status(asset_id: str) -> Reachability:
        return _reach(**COVERAGE_GAP)

    monkeypatch.setattr(agent_mod, "check_device_status", fixed_status)

    asset_id = sorted(store.assets)[0]
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")

    with _llm_agent_using(monkeypatch, FunctionModel(fn)):
        await run_llm_investigation(inc.id)

    assert any(turns), "the agent never re-asked"
    assert store.incidents[inc.id].status == "network_blindspot"
    assert store.incidents[inc.id].closed_at is not None


async def test_a_model_that_never_acts_raises_so_the_rule_agent_can_take_over(monkeypatch):
    """One re-ask, then hand over. It must not loop and must not close quietly.

    `run_investigation` only falls back because this raises. If it returned normally
    the incident would sit open forever with a full trace and no resolution — which
    reads on the dashboard as the agent still thinking.
    """
    prompts: list[bool] = []

    def fn(messages, info) -> ModelResponse:
        prompts.append(_was_re_asked(messages))
        return ModelResponse(parts=[TextPart("I would dispatch a technician.")])

    asset_id = sorted(store.assets)[0]
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")

    with _llm_agent_using(monkeypatch, FunctionModel(fn)):
        with pytest.raises(RuntimeError, match="no terminal action"):
            await run_llm_investigation(inc.id)

    # Asked twice — the original prompt and one re-ask — and then it gave up.
    assert prompts == [False, True]
    assert store.incidents[inc.id].closed_at is None


async def test_run_investigation_falls_back_to_the_rule_agent(monkeypatch):
    """The demo completes even when the model is useless.

    This is the safety net the whole `AGENT_MODE=llm` decision rests on: a model that
    refuses to act, a bad key, a dead endpoint — the incident still gets resolved by
    the deterministic agent, and the failure is recorded rather than hidden.
    """
    import app.agent as agent_pkg
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "agent_mode", "llm")

    def fn(messages, info) -> ModelResponse:
        return ModelResponse(parts=[TextPart("thinking about it")])

    asset_id = sorted(store.assets)[0]
    simulator.inject(asset_id, "hardware")
    inc = store.open_incident(asset_id, "test")
    store.set_asset_state(asset_id, "silent")

    with _llm_agent_using(monkeypatch, FunctionModel(fn)):
        await agent_pkg.run_investigation(inc.id)

    assert store.incidents[inc.id].status == "hardware_confirmed"
    assert agent_pkg.last_agent_used == "rule (fallback)"
    assert agent_pkg.last_agent_error is not None
    assert "no terminal action" in agent_pkg.last_agent_error


# ── Groq's 429 back-off ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "message, expected",
    [
        # The shape Groq actually sends on the free tier.
        (
            "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
            "`openai/gpt-oss-120b` in organization `org_x` on tokens per minute (TPM): "
            "Limit 8000, Used 7800. Please try again in 7.135s.', 'type': 'tokens', "
            "'code': 'rate_limit_exceeded'}}",
            7.635,
        ),
        # Sub-second waits are real too, and the +0.5s margin still applies.
        ("429 rate_limit_exceeded: try again in 0.5s", 1.0),
        # A rate limit we cannot parse still means "wait", not "fail".
        ("Error code: 429 - rate_limit_exceeded, slow down", 5.0),
        # Groq also formats long waits as `2m59.56s`, which this regex does not match.
        # Documented rather than asserted-away: it falls back to the 5s default, which
        # is too short but harmless — the next attempt just 429s again.
        ("429 rate_limit_exceeded: Please try again in 2m59.56s.", 5.0),
        # Never wait longer than the demo can tolerate.
        ("429 rate_limit_exceeded: Please try again in 3600s.", 20.0),
    ],
)
def test_retry_after_reads_the_wait_groq_reports(message, expected):
    """A 429 is a wait, not a failure — falling back on it abandons the real agent.

    Groq puts the exact wait in the message body and nowhere else the client exposes,
    so this parse is the only thing standing between a few seconds of patience and the
    demo silently running on the rule agent.
    """
    assert _retry_after(RuntimeError(message)) == pytest.approx(expected)


@pytest.mark.parametrize(
    "message",
    [
        "Connection refused",
        "401 invalid_api_key",
        "APIStatusError: 503 upstream unavailable",
        "",
    ],
)
def test_retry_after_ignores_everything_that_is_not_a_rate_limit(message):
    """`None` is what makes `run_investigation` stop retrying and fall back.

    Treating a bad key or a dead endpoint as a rate limit would sit through three
    sleeps before falling back — up to a minute of blank dashboard mid-demo.
    """
    assert _retry_after(RuntimeError(message)) is None


def test_retry_after_over_matches_a_bare_429():
    """Current behaviour, pinned because it is a trade-off and not obviously right.

    The detector is a substring test for "429", so any error text that merely contains
    those three digits is retried as a rate limit — three sleeps before the fallback,
    for something that was never going to succeed. Erring toward patience is the safer
    default on stage, but if this ever needs tightening, this is the test that says so.
    """
    assert _retry_after(RuntimeError("model produced 429 tokens")) == 5.0
