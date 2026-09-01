"""AI agent layer — autonomous incident investigation.

``run_investigation`` is the single entry point used by the anomaly detector and
the scenario smoke test. It picks the deterministic rule agent or the Pydantic AI
(LLM) agent from ``AGENT_MODE``; the LLM agent falls back to the rule agent on any
error so the demo always completes (Resource & Tooling Guide §11).
"""

from __future__ import annotations

import logging

from ..config import get_settings

log = logging.getLogger("agent")


# Which agent actually resolved the most recent investigation. The LLM path falls
# back to the rule path on any error, which is what you want on stage — but it also
# means a broken model config looks exactly like success. This makes it visible.
last_agent_used: str = "none"
last_agent_error: str | None = None


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

            await run_llm_investigation(incident_id)
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
