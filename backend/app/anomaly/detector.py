"""Heartbeat-freshness monitor.

When an asset's last telemetry is older than ``SILENT_THRESHOLD_SECONDS`` it is
marked ``silent``, an incident is opened, and the AI agent is dispatched to
investigate. One investigation per asset at a time.

The same sweep also runs the re-checks the agent promised. An asset closed as a
cellular blind spot is parked in ``blindspot``, which the freshness sweep skips by
design — so without something coming back for it, the "we don't send anyone, we
schedule an automated re-check" outcome left the machine dark until a human hit Reset.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from ..config import get_settings
from ..models import TraceStep, utcnow
from ..store import store

if TYPE_CHECKING:  # import-time only: agent.tools pulls in the ML client and the NaC layer
    from ..agent.tools import PendingRecheck

log = logging.getLogger("anomaly")

# How long the detector waits between freshness sweeps.
SWEEP_SECONDS = 2.0

# Stop re-checking a machine after this many failed attempts. Coverage that has not
# come back after this long is a coverage-planning problem, not something another
# poll will solve — and every attempt appends to the incident's trace, so an
# unbounded loop would grow one machine's trace without limit on a deployment that
# runs for days. The asset stays flagged, and the final step says so out loud rather
# than the re-checks just quietly stopping.
MAX_RECHECK_ATTEMPTS = 8


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
        self._rechecking: set[str] = set()
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
        from ..agent.tools import clear_rechecks

        for task in list(self._agent_tasks):
            task.cancel()
        self._agent_tasks.clear()
        self._investigating.clear()
        # Promises made about the old fleet do not survive it. (Re-checks are also
        # epoch-stamped, so a caller that resets the store without calling us — the
        # smoke script, the test fixtures — is covered too.)
        self._rechecking.clear()
        clear_rechecks()
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
                self._sweep_rechecks()
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

    # ── scheduled re-checks ───────────────────────────────────────────────
    def _sweep_rechecks(self) -> None:
        """Act on re-checks whose time has come.

        The freshness sweep above deliberately skips ``blindspot``, so this is the only
        thing that will ever look at that machine again. Without it the agent's headline
        blind-spot outcome — no dispatch, automated re-check instead — was a sentence in
        the trace and nothing else.
        """
        from ..agent.tools import cancel_recheck, due_rechecks

        for pending in due_rechecks():
            asset_id = pending.asset_id
            if asset_id in self._rechecking:
                continue  # the previous attempt is still waiting on CAMARA
            asset = store.assets.get(asset_id)
            if asset is None:
                cancel_recheck(asset_id)
                continue
            # The situation moved on without us: a transient dropout was put straight
            # back into service, or a work order was raised on the machine. Nothing to
            # re-check — but say so on the incident that promised one, rather than
            # letting the promise silently expire.
            if asset.state != "blindspot":
                if asset.state == "healthy":
                    self._trace(
                        pending.incident_id,
                        f"Scheduled re-check for {asset_id} came due — the machine is already "
                        "transmitting again, so there is nothing to re-check. Closing it out.",
                        tool="ops.schedule_recheck",
                        args={"asset_id": asset_id, "action": "cancelled"},
                        observation="asset back in service before the re-check was due",
                    )
                cancel_recheck(asset_id)
                continue
            self._rechecking.add(asset_id)
            task = asyncio.create_task(self._recheck(pending), name=f"recheck-{asset_id}")
            self._agent_tasks.add(task)
            task.add_done_callback(self._agent_tasks.discard)

    async def _recheck(self, pending: PendingRecheck) -> None:
        """Ask CAMARA again whether the network can see this machine yet.

        Two outcomes and only two. Attached to our own network again -> coverage came
        back, put it into service. Still dark -> wait the same interval and ask again.
        It never opens an incident and never dispatches: a permanently injected blind
        spot would otherwise be investigated, closed, re-checked and investigated again
        every interval for the life of the demo — a storm on the incident feed built out
        of the fix for the machine going quiet.
        """
        from ..agent.tools import (
            assess_silence,
            cancel_recheck,
            check_device_status,
            reschedule_recheck,
        )

        asset_id = pending.asset_id
        epoch = store.epoch
        try:
            reach = await check_device_status(asset_id)
        except Exception:  # noqa: BLE001
            # An unreachable API is not evidence about the machine. Try again next time,
            # and do not spend one of the attempts on a question that was never answered.
            log.exception("re-check of %s failed — will try again", asset_id)
            reschedule_recheck(pending, count_attempt=False)
            return
        finally:
            # Released as soon as the CAMARA call is done rather than at the end of the
            # function: everything below is synchronous, so no sweep can interleave and
            # start a second re-check, and every early return above would otherwise
            # leave the asset marked mid-re-check forever.
            self._rechecking.discard(asset_id)

        # The status call is the one await in here, and a presenter can hit Reset
        # across it. Writing a re-check result into a fresh fleet would resurrect a
        # machine that no longer has the problem.
        if store.epoch != epoch:
            return
        asset = store.assets.get(asset_id)
        if asset is None or asset.state != "blindspot":
            cancel_recheck(asset_id)
            return

        attempt = pending.attempts + 1
        verdict = assess_silence(reach)
        # "Back" means attached to OUR network. A device connected but roaming onto a
        # foreign operator is exactly the state the roaming ticket was raised for — its
        # telemetry still cannot reach us, so it is not back.
        # And attached with a data session. SMS-only is attached, but telemetry travels
        # over data, so a machine the operator can only reach by SMS still cannot report.
        # Counting it back put it into service, watched it go quiet again, and opened the
        # same incident a second time.
        if reach.data_connected and verdict.category != "roaming_out":
            cancel_recheck(asset_id)
            self._trace(
                pending.incident_id,
                f"Automated re-check #{attempt}: CAMARA Device Status now reports {asset_id} "
                "attached to our network. Coverage has come back and the machine was never "
                "broken — returning it to service. No technician was ever sent.",
                tool="camara.device_status",
                args={"asset_id": asset_id, "attempt": attempt},
                observation=f"status={reach.status}, source={reach.source} — back in service",
            )
            # Clearing the scenario as well as the state, via the one helper that does
            # both. Marking it healthy while the simulator still withholds the heartbeat
            # is the bug this codebase has already been bitten by twice: last_seen never
            # advances, and the detector re-opens the same incident thirty seconds later,
            # forever.
            store.resume_telemetry(asset_id)
            log.info("re-check cleared blindspot on %s after %d attempt(s)", asset_id, attempt)
            return

        if attempt >= MAX_RECHECK_ATTEMPTS:
            cancel_recheck(asset_id)
            self._trace(
                pending.incident_id,
                f"Automated re-check #{attempt}: {asset_id} is still outside coverage. "
                f"{attempt} attempts without the network coming back makes this a persistent "
                "dead zone rather than a dropout — leaving the machine flagged for coverage "
                "planning and standing down the re-check. Still no dispatch.",
                tool="camara.device_status",
                args={"asset_id": asset_id, "attempt": attempt},
                observation=f"status={reach.status} — persistent dead zone, re-check stood down",
            )
            log.info("re-check gave up on %s after %d attempts", asset_id, attempt)
            return

        next_at = reschedule_recheck(pending)
        self._trace(
            pending.incident_id,
            f"Automated re-check #{attempt}: {asset_id} "
            + (
                "is attached for SMS only, still with no data session, "
                if reach.status == "CONNECTED_SMS"
                else "is still unreachable, "
            )
            + "so the coverage gap has not cleared. Nothing has changed about the machine — "
            "waiting and asking again rather than sending anyone.",
            tool="camara.device_status",
            args={"asset_id": asset_id, "attempt": attempt, "next_at": next_at.isoformat()},
            observation=(
                f"status={reach.status}, signal={reach.signal_strength_dbm} dBm — "
                f"next re-check at {next_at:%H:%M UTC}"
            ),
        )

    def _trace(
        self,
        incident_id: str,
        thought: str,
        *,
        tool: str | None = None,
        args: dict | None = None,
        observation: str = "",
    ) -> None:
        """Report a re-check on the incident that promised it.

        Not via ``Tracer``: that numbers steps from one per instance and raises on a
        reset, both of which are right for a single investigation and wrong for
        something that comes back minutes later. Continue the existing numbering so the
        re-check reads as the next thing that happened on this incident, which is what
        it is. An incident pruned out from under us just loses the narration — the state
        change still happens.
        """
        steps = store.trace.get(incident_id)
        if steps is None:
            return
        store.add_trace_step(
            TraceStep(
                incident_id=incident_id,
                step=len(steps) + 1,
                thought=thought,
                tool=tool,
                args=args or {},
                observation=observation,
            )
        )


detector = AnomalyDetector()
