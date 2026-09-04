"""AI agent layer — autonomous incident investigation.

``run_investigation`` is the single entry point used by the anomaly detector and
the scenario smoke test. It picks the deterministic rule agent or the Pydantic AI
(LLM) agent from ``AGENT_MODE``; the LLM agent falls back to the rule agent on any
error so the demo always completes (Resource & Tooling Guide §11).
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from ..config import get_settings
from ..models import utcnow

log = logging.getLogger("agent")


# ── What each investigation actually did ─────────────────────────────────────


@dataclass(frozen=True)
class AgentReport:
    """One investigation's own record of which agent resolved it, and why.

    All there was before this was ``last_agent_used`` and ``last_agent_error``, two
    globals each assigned wherever a run happened to end. Several investigations run at
    once — the detector opens an incident per silent machine, and they arrive in a
    batch — so the pair could be assembled from two different runs: A falls back and
    writes ``"rule (fallback)"``, B then succeeds on the model and clears the error, and
    ``/api/debug/health`` reports a fallback with no reason beside it. The reverse is
    worse: B's ``"llm"`` lands on top of A's fallback and the endpoint says the model is
    running while an investigation has just silently gone without it.

    That endpoint is the documented pre-flight check for exactly that failure
    (DEMO_SCRIPT.md — Groq's daily cap makes a fallback look identical on screen), so
    each run now writes one report, whole, and never edits it afterwards. The two names
    survive as a summary of these, assigned as a pair in ``_record``.
    """

    incident_id: str
    # "llm", "rule (fallback)" or "rule" — the strings DEMO_SCRIPT.md and
    # scripts/scenario_smoke.py match on.
    agent: str
    error: str | None
    at: datetime
    # The fleet generation this investigation belonged to. A run that was still in
    # flight when someone pressed reset describes a fleet that no longer exists.
    epoch: int
    seq: int


# Keyed by incident so an investigation can be asked about by name. Bounded because a
# public deploy runs for days: this is a diagnostic tail, not a history. Incident ids
# restart at INC-0001 with each reset, so a new fleet's report replaces the old fleet's
# under the same key — which is right: that incident is gone from the store too.
_reports: dict[str, AgentReport] = {}
_report_seq = itertools.count(1)
MAX_REPORTS = 64

# What `/api/debug/health` and scripts/scenario_smoke.py read. Still two plain names —
# they are monkeypatched by the tests covering that endpoint, and a derived attribute
# cannot be — but they are no longer written independently: `_record` assigns both from
# one report, so a label can never end up beside another investigation's error.
last_agent_used: str = "none"
last_agent_error: str | None = None

# Investigations queue rather than pile on. The free-tier token budget is per minute,
# so running several at once turns a working LLM demo into a silent fallback for all
# of them; waiting a few seconds keeps every one on the real agent.
_llm_slots: asyncio.Semaphore | None = None


def _slots() -> asyncio.Semaphore:
    global _llm_slots
    if _llm_slots is None:
        _llm_slots = asyncio.Semaphore(max(1, get_settings().agent_max_concurrent))
    return _llm_slots


def _record(incident_id: str, agent: str, error: str | None, epoch: int) -> AgentReport:
    global last_agent_used, last_agent_error

    report = AgentReport(
        incident_id=incident_id,
        agent=agent,
        error=error,
        at=utcnow(),
        epoch=epoch,
        seq=next(_report_seq),
    )
    _reports[incident_id] = report
    while len(_reports) > MAX_REPORTS:
        _reports.pop(next(iter(_reports)))

    # One assignment site, both names, from one report. Whichever run wins the summary
    # below, the label and the reason came out of the same investigation.
    surfaced = _surfaced()
    last_agent_used = surfaced.agent if surfaced is not None else "none"
    last_agent_error = surfaced.error if surfaced is not None else None
    return report


def agent_report(incident_id: str) -> AgentReport | None:
    """Which agent resolved *this* incident. ``None`` if it was never investigated."""
    return _reports.get(incident_id)


def _severity(report: AgentReport) -> int:
    """How alarming a report is. Higher wins the summary below."""
    if "fallback" in report.agent:
        return 2
    return 1 if report.error else 0


def _surfaced() -> AgentReport | None:
    """The one report the health endpoint should be shown.

    Not simply the newest. The question that endpoint answers is "is the model
    actually running, or has it quietly stopped?", and the newest report cannot answer
    it while other investigations are in the air: three run, one falls back on an
    exhausted token budget, and if the other two finish after it the check reads
    ``llm`` and you walk on stage having been told the wrong thing.

    So the most degraded report wins, most recent breaking the tie — a fallback is
    never hidden by a success that merely happened later. Scoped to the current fleet
    epoch, because a reset replaces the fleet these describe: a rehearsal failure is
    not evidence about the run in front of you, and a rehearsal success is not
    permission to claim anything about it either. Per-investigation truth stays exact
    and unaggregated in ``agent_report``.
    """
    from ..store import store

    live = [r for r in _reports.values() if r.epoch == store.epoch]
    if not live:
        return None
    return max(live, key=lambda r: (_severity(r), r.seq))


# ── Groq's 429s ──────────────────────────────────────────────────────────────

# What counts as a rate limit. Deliberately not a bare "429" substring test: any error
# whose *text* happened to contain those digits — "model produced 429 tokens" — was
# treated as throttling and sat through three back-off sleeps before falling back, for
# something that was never going to succeed. Either the provider names the condition,
# or the 429 has to appear where a status code appears.
_RATE_LIMITED = re.compile(
    r"rate[ _-]?limit"
    r"|too many requests"
    r"|\b(?:error|status|http)[ _]?(?:code)?\W{0,3}429\b"
    r"|^\s*429\b",
    re.IGNORECASE,
)

# Groq formats anything over a minute as `try again in 2m59.56s`. A seconds-only
# pattern does not match that at all, so the parse silently fell through to the 5s
# default and all three attempts burned inside a window the server had just said was
# three minutes long — the fallback the retry exists to avoid, arrived at slowly.
_RETRY_IN = re.compile(r"try again in (?:([0-9]+)m)?([0-9.]+)s", re.IGNORECASE)


def _retry_after(exc: Exception) -> float | None:
    """Groq reports 429s with the wait built into the message; honour it."""
    text = str(exc)
    if not _RATE_LIMITED.search(text):
        return None
    m = _RETRY_IN.search(text)
    if m is None:
        return 5.0
    wait = 60.0 * int(m.group(1) or 0) + float(m.group(2))
    # Still capped: a three-minute wait is not something a demo sits through, and the
    # rule agent resolves the incident correctly the moment we stop waiting.
    return min(wait + 0.5, 20.0)


class StaleInvestigation(RuntimeError):
    """The fleet was reset while this investigation was in flight."""


def _already_resolved(incident_id: str, why: str) -> bool:
    """Has this incident already been closed by the run we are about to repeat?

    The agent's terminal tools mutate the store from *inside* the Pydantic AI run:
    they create the work order, claim the technician and close the incident, and only
    then does Pydantic AI make one more model call to write its final text. If that
    last call is the one that 429s — exactly the case the retry below exists for — the
    exception surfaces after the dispatch has already landed, and re-running the
    investigation issues a second work order, marks a second technician busy, and
    double-counts both `dispatches_issued` and the triage-duration sample. Wiping the
    trace on the way in hides all of it: the operator sees one clean investigation.

    So every path that re-enters an investigation asks this first. Logged at INFO,
    naming the incident, so a swallowed double-run leaves a mark instead of vanishing.
    """
    from ..store import store

    inc = store.incidents.get(incident_id)
    if inc is None or inc.closed_at is None:
        return False
    log.info(
        "not re-running %s (%s) — already closed as %s at %s; a terminal tool landed "
        "before the run ended",
        incident_id, why, inc.status, inc.closed_at.isoformat(),
    )
    return True


async def run_investigation(incident_id: str) -> None:
    from ..store import store

    epoch = store.epoch
    settings = get_settings()
    llm_error: str | None = None
    if settings.agent_mode == "llm":
        try:
            from .agent import run_llm_investigation

            # A rate limit is a "wait", not a failure. Falling back on the first one
            # would abandon the real agent for a few seconds of patience.
            #
            # The slot is taken per *attempt*, and released before the back-off sleep.
            # With the sleep inside it, one throttled investigation held the only slot
            # for up to 40 seconds across two waits, and every other silent machine on
            # the site queued behind it — the detector's incidents arrive together, so
            # this is the normal case, not the unlucky one. Waiting outside the slot
            # lets the next investigation use the token budget this one is sitting out,
            # and the retry re-queues behind whoever took it.
            resolved_despite: str | None = None
            for attempt in range(3):
                try:
                    async with _slots():
                        await run_llm_investigation(incident_id)
                    break
                except Exception as exc:  # noqa: BLE001
                    wait = _retry_after(exc)
                    if wait is None or attempt == 2 or store.epoch != epoch:
                        raise
                    # Checked before the trace reset below, not after: if the
                    # dispatch already landed, that trace is the evidence of it.
                    if _already_resolved(incident_id, "rate-limit retry"):
                        # The model's own tools resolved it, so the report says "llm" —
                        # but it says so carrying the 429, because being throttled is
                        # the thing the pre-flight check is looking for.
                        resolved_despite = f"{type(exc).__name__}: {exc}"
                        break
                    log.warning(
                        "rate limited on %s — retrying in %.1fs (attempt %d)",
                        incident_id, wait, attempt + 1,
                    )
                    store.trace[incident_id] = []
                    await asyncio.sleep(wait)
            _record(incident_id, "llm", resolved_despite, epoch)
            return
        except StaleInvestigation:
            log.info("dropping %s — fleet was reset mid-investigation", incident_id)
            return
        except Exception as exc:  # noqa: BLE001
            llm_error = f"{type(exc).__name__}: {exc}"
            log.exception("LLM agent failed for %s — falling back to rule agent", incident_id)
            if store.epoch != epoch:
                # Stamped with the epoch it ran in, so it stays out of the health
                # endpoint's account of the *current* fleet — it describes machines
                # that no longer exist — while `agent_report` can still be asked what
                # became of this incident.
                _record(incident_id, "llm", llm_error, epoch)
                return
            # Same reasoning as the retry guard, and again before the trace reset: the
            # run can throw *after* a terminal tool has closed the incident. The LLM
            # agent's tools are what resolved it, so record that — but keep the error
            # on the same report, because the run did fail and the debug endpoint is
            # the only place that failure is visible.
            if _already_resolved(incident_id, "rule-agent fallback"):
                _record(incident_id, "llm", llm_error, epoch)
                return
            # Drop the abandoned partial trace. The rule agent re-runs the whole
            # investigation, and leaving both in place shows the operator two
            # interleaved step-1s for a single incident.
            store.trace[incident_id] = []

    if store.epoch != epoch:
        log.info("dropping %s — fleet was reset mid-investigation", incident_id)
        return

    from .rule_agent import run_rule_investigation

    # The backstop. Every route into the rule agent — the LLM fallback above and a
    # plain AGENT_MODE=rule call — passes through this line, so no path can re-open a
    # closed incident by going around the guards above. On a first investigation the
    # incident is open and this costs a dict lookup.
    if _already_resolved(incident_id, "rule agent entry"):
        return

    try:
        await run_rule_investigation(incident_id)
    except StaleInvestigation:
        log.info("dropping %s — fleet was reset mid-investigation", incident_id)
        return
    # `llm_error` is None in plain rule mode and carries the model's failure on the
    # fallback path, so the label and the reason always describe this one run.
    _record(
        incident_id,
        "rule (fallback)" if settings.agent_mode == "llm" else "rule",
        llm_error,
        epoch,
    )


__all__ = [
    "AgentReport",
    "StaleInvestigation",
    "agent_report",
    "last_agent_error",
    "last_agent_used",
    "run_investigation",
]
