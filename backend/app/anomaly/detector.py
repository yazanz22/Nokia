"""Heartbeat-freshness monitor.

When an asset's last telemetry is older than ``SILENT_THRESHOLD_SECONDS`` it is
marked ``silent``, an incident is opened, and the AI agent is dispatched to
investigate. One investigation per asset at a time.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from ..config import get_settings
from ..models import utcnow
from ..store import store

log = logging.getLogger("anomaly")


class AnomalyDetector:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._investigating: set[str] = set()
        self._agent_tasks: set[asyncio.Task] = set()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="anomaly-detector")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        for t in list(self._agent_tasks):
            t.cancel()

    def reset(self) -> None:
        """Abandon anything in flight.

        A reset means "start clean". An investigation already running would
        otherwise finish a few seconds later and write its work order into the
        fresh state — a phantom dispatch on an untouched fleet.
        """
        for task in list(self._agent_tasks):
            task.cancel()
        self._agent_tasks.clear()
        self._investigating.clear()

    async def _run(self) -> None:
        settings = get_settings()
        while True:
            threshold = settings.silent_threshold_seconds
            now = utcnow()
            for asset_id, asset in list(store.assets.items()):
                if asset_id in self._investigating:
                    continue
                if asset.state in ("blindspot", "dispatched", "silent"):
                    continue
                age = (now - asset.last_seen).total_seconds()
                if age >= threshold:
                    self._trigger(asset_id, age)
            await asyncio.sleep(2.0)

    def _trigger(self, asset_id: str, age: float) -> None:
        self._investigating.add(asset_id)
        store.set_asset_state(asset_id, "silent")
        inc = store.open_incident(
            asset_id,
            summary=f"Telemetry stream from {asset_id} went dark "
            f"({age:.0f}s since last heartbeat).",
        )
        log.info("opened %s for %s", inc.id, asset_id)

        from ..agent import run_investigation  # local import avoids a cycle

        task = asyncio.create_task(self._investigate(asset_id, inc.id), name=f"agent-{inc.id}")
        self._agent_tasks.add(task)
        task.add_done_callback(self._agent_tasks.discard)

    async def _investigate(self, asset_id: str, incident_id: str) -> None:
        from ..agent import run_investigation

        try:
            await run_investigation(incident_id)
        except Exception:  # noqa: BLE001
            log.exception("investigation for %s failed", incident_id)
        finally:
            self._investigating.discard(asset_id)


detector = AnomalyDetector()
