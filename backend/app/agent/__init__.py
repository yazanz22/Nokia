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
            # Drop the abandoned partial trace. The rule agent re-runs the whole
            # investigation, and leaving both in place shows the operator two
            # interleaved step-1s for a single incident.
            store.trace[incident_id] = []

    if store.epoch != epoch:
        log.info("dropping %s — fleet was reset mid-investigation", incident_id)
        return

    from .rule_agent import run_rule_investigation

    try:
        await run_rule_investigation(incident_id)
    except StaleInvestigation:
        log.info("dropping %s — fleet was reset mid-investigation", incident_id)
        return
    last_agent_used = "rule (fallback)" if settings.agent_mode == "llm" else "rule"


__all__ = ["run_investigation", "last_agent_used", "last_agent_error"]
