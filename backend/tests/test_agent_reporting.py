"""Who resolved which incident, and which source answered which call.

Both questions are asked by a human immediately before a demo — `/api/debug/health`
for "is the model actually running or has it silently fallen back?" (the demo's
pre-flight checklist) and `/api/debug/nac` for "is this integration real?". Both used
to be answered by a single mutable field that whichever run finished last had
overwritten, so the answer could belong to a different investigation than the question.
These tests pin the answers to the run they describe.
"""

from __future__ import annotations

import asyncio
import time

import pytest

import app.agent as agent_pkg
from app.agent import agent as llm_agent_mod
from app.config import get_settings
from app.models import utcnow
from app.nac.base import DeviceLocation, Reachability
from app.nac.factory import FallbackNaCClient
from app.simulator import simulator
from app.store import store


# ── The agent behind each investigation ──────────────────────────────────────


@pytest.fixture
def llm_mode(monkeypatch):
    """AGENT_MODE=llm with a scripted `run_llm_investigation` and a single slot.

    conftest pins the suite to the rule agent; the reporting only has anything to
    report about when the LLM path is the one being taken.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_mode", "llm")
    monkeypatch.setattr(settings, "agent_max_concurrent", 1)
    # Built lazily from the setting above, and cached across tests — rebuild it so this
    # test's concurrency is the one it configured.
    monkeypatch.setattr(agent_pkg, "_llm_slots", None)
    yield settings


def _open(scenario: str = "hardware") -> tuple[str, str]:
    """A real silent asset with a real open incident, ready to be investigated."""
    asset_id = next(
        a for a in sorted(store.assets)
        if store.assets[a].state == "healthy" and not simulator.is_silent(a)
    )
    simulator.inject(asset_id, scenario)
    inc = store.open_incident(asset_id, summary=f"[reporting] {asset_id} silent")
    store.set_asset_state(asset_id, "silent")
    return asset_id, inc.id


async def test_a_fallback_is_not_hidden_by_the_investigation_that_finishes_after_it(
    monkeypatch, llm_mode
):
    """The health check must not say "llm" while a run has just gone without it.

    This is the failure the endpoint exists to catch: Groq's daily cap is reached, one
    investigation falls back to the rule agent, and a second — which happened to be
    cheap enough to still fit in the budget — finishes afterwards and overwrites the
    record. The output on screen is identical and correct either way, so the endpoint
    is the only place the fallback is visible, and it was reporting the wrong run.
    """
    fell_back_id = None

    async def fake_llm(incident_id: str) -> None:
        if incident_id == fell_back_id:
            raise RuntimeError("no terminal action")

    monkeypatch.setattr(llm_agent_mod, "run_llm_investigation", fake_llm)

    _, fell_back_id = _open("hardware")
    _, worked_id = _open("blindspot")

    await agent_pkg.run_investigation(fell_back_id)
    await agent_pkg.run_investigation(worked_id)  # finishes last, on the real model

    assert agent_pkg.last_agent_used == "rule (fallback)"
    assert "no terminal action" in agent_pkg.last_agent_error


async def test_the_reported_error_belongs_to_the_reported_run(monkeypatch, llm_mode):
    """Label and reason come from one report, so they cannot be assembled from two runs.

    As two independent globals, a success landing between a fallback's two writes left
    `last_agent_used="rule (fallback)"` beside `last_agent_error=None` — a fallback with
    no reason given, on an endpoint whose whole job is to give the reason.
    """
    failing_id = None

    async def fake_llm(incident_id: str) -> None:
        if incident_id == failing_id:
            raise RuntimeError("groq: invalid api key")

    monkeypatch.setattr(llm_agent_mod, "run_llm_investigation", fake_llm)

    _, failing_id = _open("hardware")
    _, ok_id = _open("blindspot")

    # Concurrently, and deliberately interleaved: one slot, so they finish in an order
    # neither of them controls.
    await asyncio.gather(
        agent_pkg.run_investigation(failing_id),
        agent_pkg.run_investigation(ok_id),
    )

    used, error = agent_pkg.last_agent_used, agent_pkg.last_agent_error
    assert used == "rule (fallback)"
    assert error is not None and "invalid api key" in error

    # And each investigation still answers for itself, unaggregated.
    assert agent_pkg.agent_report(failing_id).agent == "rule (fallback)"
    assert "invalid api key" in agent_pkg.agent_report(failing_id).error
    assert agent_pkg.agent_report(ok_id).agent == "llm"
    assert agent_pkg.agent_report(ok_id).error is None


async def test_a_healthy_llm_run_reports_itself(monkeypatch, llm_mode):
    """The green case, which the checklist reads as permission to go on stage."""

    async def fake_llm(incident_id: str) -> None:
        return None

    monkeypatch.setattr(llm_agent_mod, "run_llm_investigation", fake_llm)

    _, incident_id = _open("blindspot")
    await agent_pkg.run_investigation(incident_id)

    assert agent_pkg.last_agent_used == "llm"
    assert agent_pkg.last_agent_error is None


async def test_a_rehearsal_fallback_does_not_condemn_the_fleet_that_replaced_it(
    monkeypatch, llm_mode
):
    """Reports are scoped to the fleet they describe.

    Otherwise the summary is sticky: one fallback during rehearsal and the pre-flight
    check reads ``rule (fallback)`` for the rest of the process, over a fresh fleet
    whose every investigation ran on the model. The reset that cleared the incidents
    those reports name is what makes them stop counting.
    """
    # Incident ids restart at INC-0001 with the fleet, so the rehearsal is two
    # investigations: the second one's report keeps its own key across the reset and is
    # the one that would still be counted if reports were not scoped to a fleet.
    calls = 0

    async def fake_llm(incident_id: str) -> None:
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise RuntimeError("no terminal action")

    monkeypatch.setattr(llm_agent_mod, "run_llm_investigation", fake_llm)

    for scenario in ("hardware", "blindspot"):
        _, rehearsal_id = _open(scenario)
        await agent_pkg.run_investigation(rehearsal_id)
    stale_id = rehearsal_id
    assert agent_pkg.last_agent_used == "rule (fallback)"

    store.reset()  # the presenter starts the real run

    _, fresh_id = _open("blindspot")
    await agent_pkg.run_investigation(fresh_id)

    assert agent_pkg.agent_report(stale_id).epoch != store.epoch
    assert agent_pkg.last_agent_used == "llm"
    assert agent_pkg.last_agent_error is None


async def test_a_throttled_investigation_does_not_hold_the_only_slot(monkeypatch, llm_mode):
    """The back-off waits outside the semaphore, not inside it.

    `agent_max_concurrent=1` exists so several investigations cannot blow the per-minute
    token budget together. With the two retry sleeps taken inside that slot, one
    throttled investigation froze every other one for up to 40 seconds — and the
    detector opens incidents in batches, so that is the ordinary case. The machine
    behind it in the queue is silent for a reason nobody is looking into yet.
    """
    order: list[str] = []
    since_throttle: dict[str, float] = {}
    throttled = asyncio.Event()
    throttled_at = 0.0
    first_attempt = True
    slow_id = None

    async def fake_llm(incident_id: str) -> None:
        nonlocal first_attempt, throttled_at
        if incident_id == slow_id and first_attempt:
            first_attempt = False
            order.append("throttled")
            throttled_at = time.perf_counter()
            throttled.set()
            # Parsed as 0.5 + the 0.5s margin: a full second of back-off to fit inside.
            raise RuntimeError("429 rate_limit_exceeded: Please try again in 0.5s")
        order.append(incident_id)
        since_throttle[incident_id] = time.perf_counter() - throttled_at

    monkeypatch.setattr(llm_agent_mod, "run_llm_investigation", fake_llm)

    _, slow_id = _open("hardware")
    _, other_id = _open("blindspot")

    slow = asyncio.create_task(agent_pkg.run_investigation(slow_id))
    await throttled.wait()  # the slot is now free and the back-off is running
    other = asyncio.create_task(agent_pkg.run_investigation(other_id))
    await asyncio.gather(slow, other)

    # The second investigation ran *during* the first one's back-off, not after it.
    assert order == ["throttled", other_id, slow_id]
    assert since_throttle[other_id] < 0.5, (
        f"waited out the back-off before getting the slot: {since_throttle[other_id]:.2f}s"
    )
    assert agent_pkg.agent_report(slow_id).agent == "llm"


# ── Which source answered a CAMARA call ──────────────────────────────────────


class _StubClient:
    """A NetworkClient that answers, or raises for the assets it is told to fail on."""

    def __init__(self, source: str, fail_assets: set[str] | None = None,
                 fail_calls: set[str] | None = None) -> None:
        self.source = source
        self.fail_assets = fail_assets or set()
        self.fail_calls = fail_calls or set()

    def _maybe_fail(self, call: str, asset_id: str) -> None:
        if asset_id in self.fail_assets or call in self.fail_calls:
            raise RuntimeError(f"sandbox timeout on {call} for {asset_id}")

    async def get_reachability(self, asset_id: str) -> Reachability:
        self._maybe_fail("reachability", asset_id)
        return Reachability(asset_id=asset_id, status="NOT_CONNECTED", as_of=utcnow(),
                            source=self.source)

    async def get_location(self, asset_id: str) -> DeviceLocation:
        self._maybe_fail("location", asset_id)
        return DeviceLocation(asset_id=asset_id, latitude=27.5, longitude=34.9,
                              accuracy_m=50.0, as_of=utcnow(), source=self.source)


async def test_one_flows_fallback_does_not_relabel_another_flows_live_answer():
    """`/api/debug/nac` answers "is this integration real?" — for its own call.

    The client is a process-wide singleton every investigation shares, so a mock
    fallback for some machine the sandbox has never heard of used to overwrite the one
    `last_source` field mid-request, and the endpoint reported the other flow's source
    over its own result. Each caller now sees only what its own calls did.
    """
    client = FallbackNaCClient(
        live=_StubClient("live", fail_assets={"EQ-MOCKED"}), mock=_StubClient("mock")
    )
    gate_a, gate_b = asyncio.Event(), asyncio.Event()

    async def flow(asset_id: str, mine: asyncio.Event, theirs: asyncio.Event) -> str:
        r = await client.get_reachability(asset_id)
        mine.set()
        await theirs.wait()  # both calls have now landed; read afterwards
        return f"{r.source}/{client.last_source}"

    live_flow, mock_flow = await asyncio.gather(
        flow("EQ-0001", gate_a, gate_b),
        flow("EQ-MOCKED", gate_b, gate_a),
    )

    assert live_flow == "live/live"
    assert mock_flow == "mock/mock"


async def test_a_half_live_answer_says_which_half():
    """Reachability from the sandbox, location from the dataset, is not "live".

    The endpoint makes two calls and reports one source. Collapsing a split result to
    whichever call happened to be written last claims a network-verified coordinate for
    one the mock invented — the precise claim the panel exists to substantiate.
    """
    client = FallbackNaCClient(
        live=_StubClient("live", fail_calls={"location"}), mock=_StubClient("mock")
    )

    reach = await client.get_reachability("EQ-0001")
    loc = await client.get_location("EQ-0001")

    assert (reach.source, loc.source) == ("live", "mock")
    assert client.last_source == "mixed: location=mock, reachability=live"
    assert client.last_call_sources == {"reachability": "live", "location": "mock"}


async def test_the_source_is_unknown_before_anything_is_asked():
    """No call, no claim — rather than the constructor's optimistic "live"."""
    client = FallbackNaCClient(live=_StubClient("live"), mock=_StubClient("mock"))
    assert client.last_source == "unknown"
