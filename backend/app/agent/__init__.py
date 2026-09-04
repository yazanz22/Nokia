"""AI agent layer — autonomous incident investigation.

``run_investigation`` is the single entry point used by the anomaly detector and
the scenario smoke test. It picks the deterministic rule agent or the Pydantic AI
(LLM) agent from ``AGENT_MODE``; the LLM agent falls back to the rule agent on any
error so the demo always completes (Resource & Tooling Guide §11).
"""

from __future__ import annotations

import asyncio
import logging
import re

from ..config import get_settings

log = logging.getLogger("agent")


# Which agent actually resolved the most recent investigation. The LLM path falls
# back to the rule path on any error, which is what you want on stage — but it also
# means a broken model config looks exactly like success. This makes it visible.
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


def _retry_after(exc: Exception) -> float | None:
    """Groq reports 429s with the wait built into the message; honour it."""
    text = str(exc)
    if "rate_limit" not in text and "429" not in text:
        return None
    m = re.search(r"try again in ([0-9.]+)s", text)
    return min(float(m.group(1)) + 0.5, 20.0) if m else 5.0


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
    global last_agent_used, last_agent_error
    from ..store import store

    epoch = store.epoch
    settings = get_settings()
    if settings.agent_mode == "llm":
        try:
            from .agent import run_llm_investigation

            async with _slots():
                # A rate limit is a "wait", not a failure. Falling back on the first one
                # would abandon the real agent for a few seconds of patience.
                for attempt in range(3):
                    try:
                        await run_llm_investigation(incident_id)
                        break
                    except Exception as exc:  # noqa: BLE001
                        wait = _retry_after(exc)
                        if wait is None or attempt == 2 or store.epoch != epoch:
                            raise
                        # Checked before the trace reset below, not after: if the
                        # dispatch already landed, that trace is the evidence of it.
                        if _already_resolved(incident_id, "rate-limit retry"):
                            break
                        log.warning(
                            "rate limited on %s — retrying in %.1fs (attempt %d)",
                            incident_id, wait, attempt + 1,
                        )
                        store.trace[incident_id] = []
                        await asyncio.sleep(wait)
            last_agent_used = "llm"
            last_agent_error = None
            return
        except StaleInvestigation:
            log.info("dropping %s — fleet was reset mid-investigation", incident_id)
            return
        except Exception as exc:  # noqa: BLE001
            last_agent_error = f"{type(exc).__name__}: {exc}"
            log.exception("LLM agent failed for %s — falling back to rule agent", incident_id)
            if store.epoch != epoch:
                return
            # Same reasoning as the retry guard, and again before the trace reset: the
            # run can throw *after* a terminal tool has closed the incident. The LLM
            # agent's tools are what resolved it, so record that — but leave
            # `last_agent_error` set, because the run did fail and the debug endpoint
            # is the only place that failure is visible.
            if _already_resolved(incident_id, "rule-agent fallback"):
                last_agent_used = "llm"
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
    last_agent_used = "rule (fallback)" if settings.agent_mode == "llm" else "rule"


__all__ = ["run_investigation", "last_agent_used", "last_agent_error"]
