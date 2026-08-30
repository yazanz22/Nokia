"""Helper for emitting the agent's step-by-step reasoning trace.

Every step is persisted on the incident and streamed to the dashboard, where the
``AgentTrace`` panel renders it live — judges love seeing the "thinking"
(Resource & Tooling Guide §11).
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..models import TraceStep
from ..store import store


class Tracer:
    def __init__(self, incident_id: str, *, step_delay: float = 0.7) -> None:
        self.incident_id = incident_id
        self._n = 0
        self._delay = step_delay

    async def step(
        self,
        thought: str,
        *,
        tool: str | None = None,
        args: dict[str, Any] | None = None,
        observation: str = "",
    ) -> None:
        self._n += 1
        store.add_trace_step(
            TraceStep(
                incident_id=self.incident_id,
                step=self._n,
                thought=thought,
                tool=tool,
                args=args or {},
                observation=observation,
            )
        )
        # A small pause makes the trace readable as it streams on stage.
        if self._delay:
            await asyncio.sleep(self._delay)
