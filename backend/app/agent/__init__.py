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


async def run_investigation(incident_id: str) -> None:
    settings = get_settings()
    if settings.agent_mode == "llm":
        try:
            from .agent import run_llm_investigation

            await run_llm_investigation(incident_id)
            return
        except Exception:  # noqa: BLE001
            log.exception("LLM agent failed for %s — falling back to rule agent", incident_id)
    from .rule_agent import run_rule_investigation

    await run_rule_investigation(incident_id)


__all__ = ["run_investigation"]
