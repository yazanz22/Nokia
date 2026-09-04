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

# How long the detector waits between freshness sweeps.
SWEEP_SECONDS = 2.0


def _log_task_exit(task: asyncio.Task) -> None:
    """Say something out loud if the sweep loop ever stops.

    ``self._task`` holds a strong reference, so asyncio's "Task exception was never
    retrieved" warning waits for garbage collection that never comes for a module-level
    singleton. A detector that died stopped opening incidents entirely and said nothing
    — silent machines simply never got investigated. Cancellation is how stop() ends the
    loop, so that one is not a failure.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.critical("anomaly detector died — silent assets are no longer noticed", exc_info=exc)
    else:
        log.critical("anomaly detector returned unexpectedly — silent assets are no longer noticed")


class AnomalyDetector:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._investigating: set[str] = set()
        self._agent_tasks: set[asyncio.Task] = set()

    def start(self) -> None:
        self._ensure_running()

    def _ensure_running(self) -> None:
        """(Re)create the sweep task unless a live one is already there.

        A task that raised is ``done()``, not running, and nothing distinguishes a dead
        task in ``self._task`` from a live one — which is how one bad sweep used to stop
        every future investigation for the life of the process. Replacing a finished task
        here is what lets reset() bring the detector back.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Nothing to schedule on: reset() is reachable from synchronous test and
            # script code. Boot calls start() from inside the lifespan, where a loop
            # always exists.
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="anomaly-detector")
            self._task.add_done_callback(_log_task_exit)

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
        # A reset is the operator saying "make it work again". If an earlier sweep threw
        # its way out of the loop, clearing the in-flight state would hand back a clean
        # fleet that nobody is watching any more.
        self._ensure_running()

    async def _run(self) -> None:
        settings = get_settings()
        while True:
            # A sweep that throws — a store mutated underneath us, an asset with no
            # last_seen — must not take the detector with it. Log it and sweep again;
            # the sleep is outside the try so a sweep that fails every time cannot
            # become a hot loop.
            try:
                self._sweep(settings.silent_threshold_seconds)
            except Exception:  # noqa: BLE001
                log.exception("anomaly sweep failed — skipping this pass")
            await asyncio.sleep(SWEEP_SECONDS)

    def _sweep(self, threshold: float) -> None:
        now = utcnow()
        for asset_id, asset in list(store.assets.items()):
            if asset_id in self._investigating:
                continue
            if asset.state in ("blindspot", "dispatched", "silent"):
                continue
            age = (now - asset.last_seen).total_seconds()
            if age >= threshold:
                self._trigger(asset_id, age)

    def _trigger(self, asset_id: str, age: float) -> None:
        self._investigating.add(asset_id)
        store.set_asset_state(asset_id, "silent")
        inc = store.open_incident(
            asset_id,
            summary=f"Telemetry stream from {asset_id} went dark "
            f"({age:.0f}s since last heartbeat).",
        )
        log.info("opened %s for %s", inc.id, asset_id)

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
