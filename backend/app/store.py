"""In-memory application state for the prototype.

Single-process, single-writer (the asyncio event loop). No database — the demo
starts from a clean, deterministic seed every time. Every mutation publishes a
``WsEvent`` so connected dashboards stay in sync.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from datetime import datetime
from weakref import WeakKeyDictionary

from .events import bus
from .models import (
    Asset,
    AssetState,
    GeofenceAlert,
    Incident,
    Kpis,
    Technician,
    TelemetrySample,
    TraceStep,
    Warehouse,
    WorkOrder,
    WsEvent,
    utcnow,
)
from .seed import build_demo_fleet, build_technicians, build_warehouses

log = logging.getLogger("store")


def _current_task() -> asyncio.Task | None:
    """The task we are being called from, if there is a loop at all.

    Reset, the scenario routes and a good deal of the test suite reach the store from
    plain synchronous code, where there is no task to attribute anything to.
    """
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


def _dead_zones() -> list[dict]:
    # Imported lazily: memory lives in the agent package, which imports the store.
    from .agent.memory import memory

    return memory.dead_zones()


# A public deployment runs for days with nobody pressing reset, and every incident
# carries a trace. Keeping the most recent slice bounds memory without affecting
# anything a viewer can see — the dashboard only ever shows recent activity.
MAX_INCIDENTS = 200
MAX_WORK_ORDERS = 200


class Store:
    def __init__(self) -> None:
        # Bumped on every reset. An investigation started before a reset must not be
        # allowed to write its result into the fresh state afterwards — otherwise a
        # presenter who resets mid-run gets a phantom work order on a clean fleet.
        self.epoch = 0
        self.assets: dict[str, Asset] = {}
        self.technicians: dict[str, Technician] = {}
        self.warehouses: dict[str, Warehouse] = {}
        self.incidents: dict[str, Incident] = {}
        # Which epoch each in-flight investigation is reasoning about, keyed by the task
        # running it and stamped every time that task narrates a step. Deliberately not
        # cleared by reset() — surviving the reset is the entire point; see
        # ``add_work_order``. Weak keys, so an investigation's entry goes when its task
        # does and a deployment that runs for days does not accumulate them.
        self._task_epoch: WeakKeyDictionary[asyncio.Task, int] = WeakKeyDictionary()
        self.trace: dict[str, list[TraceStep]] = {}
        self.work_orders: dict[str, WorkOrder] = {}
        self.geofence_alerts: dict[str, GeofenceAlert] = {}
        self.latest_telemetry: dict[str, TelemetrySample] = {}
        self._incident_seq = itertools.count(1)
        self._wo_seq = itertools.count(1)
        self._gf_seq = itertools.count(1)
        # KPI counters that persist across the session
        self.false_dispatches_avoided = 0
        self.incidents_prevented = 0
        self.dispatches_issued = 0
        self.no_fault_found = 0
        self._triage_durations: list[float] = []
        self.reset()

    # ── lifecycle ──────────────────────────────────────────────────────────
    def reset(self) -> None:
        self.epoch += 1
        self.assets = {a.id: a for a in build_demo_fleet()}
        self.technicians = {t.id: t for t in build_technicians()}
        # Stock comes back with the fleet. A depot whose shelves stayed empty across a
        # reset would make the second run of a demo behave differently from the first,
        # which is the class of thing that only ever shows up on stage.
        self.warehouses = {w.id: w for w in build_warehouses()}
        self.incidents.clear()
        self.trace.clear()
        self.work_orders.clear()
        self.geofence_alerts.clear()
        self.latest_telemetry.clear()
        self._incident_seq = itertools.count(1)
        self._wo_seq = itertools.count(1)
        self._gf_seq = itertools.count(1)
        self.false_dispatches_avoided = 0
        self.incidents_prevented = 0
        self.dispatches_issued = 0
        self.no_fault_found = 0
        self._triage_durations.clear()

    # ── assets / telemetry ────────────────────────────────────────────────
    def set_asset_state(self, asset_id: str, state: AssetState, *, last_seen: datetime | None = None) -> None:
        asset = self.assets[asset_id]
        asset.state = state
        if last_seen is not None:
            asset.last_seen = last_seen
        bus.publish(WsEvent(type="asset_update", payload=asset.model_dump(mode="json")))

    def record_telemetry(self, sample: TelemetrySample) -> None:
        self.latest_telemetry[sample.asset_id] = sample
        asset = self.assets.get(sample.asset_id)
        if asset and asset.state in ("healthy", "anomaly"):
            asset.last_seen = sample.ts
        bus.publish(WsEvent(type="telemetry", payload=sample.model_dump(mode="json")))

    # ── incidents ─────────────────────────────────────────────────────────
    def open_incident(self, asset_id: str, summary: str) -> Incident:
        inc = Incident(id=f"INC-{next(self._incident_seq):04d}", asset_id=asset_id, summary=summary)
        self.incidents[inc.id] = inc
        self.trace[inc.id] = []
        self._prune()
        bus.publish(WsEvent(type="incident_update", payload=inc.model_dump(mode="json")))
        return inc

    def update_incident(self, inc: Incident) -> None:
        self.incidents[inc.id] = inc
        bus.publish(WsEvent(type="incident_update", payload=inc.model_dump(mode="json")))

    def close_incident(self, inc: Incident, status: str, resolution: str) -> None:
        # An incident closes once. Two terminal tool calls from a single model turn
        # (Pydantic AI runs them in parallel) would otherwise overwrite the resolution,
        # append a second triage sample — dragging the average MTTR the dashboard shows
        # toward whichever run finished second — and re-publish the incident, so the
        # operator watches one machine get resolved twice. The callers guard themselves
        # too, but this makes "closed once" a property of the store rather than
        # something every caller has to remember.
        if inc.closed_at is not None:
            return
        inc.status = status  # type: ignore[assignment]
        inc.resolution = resolution
        inc.closed_at = utcnow()
        if inc.opened_at and inc.closed_at:
            self._triage_durations.append((inc.closed_at - inc.opened_at).total_seconds())
        self.update_incident(inc)

    def _prune(self) -> None:
        """Drop the oldest incidents, their traces and their work orders."""
        if len(self.incidents) > MAX_INCIDENTS:
            keep = sorted(self.incidents.values(), key=lambda i: i.opened_at)[-MAX_INCIDENTS:]
            keep_ids = {i.id for i in keep}
            self.incidents = {i.id: i for i in keep}
            self.trace = {k: v for k, v in self.trace.items() if k in keep_ids}
        if len(self.work_orders) > MAX_WORK_ORDERS:
            kept = sorted(self.work_orders.values(), key=lambda w: w.created_at)[-MAX_WORK_ORDERS:]
            self.work_orders = {w.id: w for w in kept}
        # Only the mean matters, so a rolling window is enough.
        if len(self._triage_durations) > 500:
            del self._triage_durations[:-500]

    def add_trace_step(self, step: TraceStep) -> None:
        # Every step an investigation narrates is a store write made from inside the
        # task running it, which makes this the one place the store can learn which
        # fleet that task is reasoning about — without the callers having to tell it.
        # ``add_work_order`` reads it back; see there for what it is for.
        task = _current_task()
        if task is not None:
            self._task_epoch[task] = self.epoch
        self.trace.setdefault(step.incident_id, []).append(step)
        bus.publish(WsEvent(type="trace_step", payload=step.model_dump(mode="json")))

    # ── work orders ───────────────────────────────────────────────────────
    def next_work_order_id(self) -> str:
        return f"WO-{next(self._wo_seq):04d}"

    def claim_technician(self, tech: Technician) -> bool:
        """Take a technician off the board. False means somebody else got there first.

        Availability used to be flipped down in ``add_work_order``, which is the last
        line of a dispatch rather than the first — and by then it is far too late.
        ``create_work_order`` reads the free crew, then spends ~3.6s asking CAMARA
        Location Retrieval where each of them is, and only then decides who goes. Two
        investigations overlapping in that window both read the same free list and both
        picked the same nearest name: ``WO-0002 EQ-0008 -> Ziad Khalifeh`` and
        ``WO-0003 EQ-0022 -> Ziad Khalifeh``, 90 km one way and 33 km the other. Two
        clicks a few seconds apart is all it takes — that is inside the 4/min rate limit,
        so nothing upstream stops it either.

        The test-and-set here is what actually decides it. It is synchronous, so the
        event loop cannot interleave the check and the flip, and exactly one caller can
        win. Callers must select from the *currently* available crew and claim in the
        same synchronous block — see ``create_work_order``. Same shape, and the same
        reason, as ``_claim_terminal`` in ``agent/agent.py``: that one stops one incident
        being resolved twice, this one stops two incidents booking one technician.
        """
        if not tech.available:
            return False
        tech.available = False
        self.publish_technicians()
        return True

    def stock_on_hand(self, part: str) -> dict[str, int]:
        """Which depots hold ``part`` right now, id → units. Empty means nobody does."""
        return {
            w.id: w.stock[part]
            for w in self.warehouses.values()
            if w.stock.get(part, 0) > 0
        }

    def depots_stocking(self, parts: list[str]) -> list[str]:
        """Depots holding *every* one of ``parts`` right now.

        All-or-nothing on purpose. A visit that needs a component and a service kit is
        one journey to one depot; a depot holding half the list cannot serve it, and
        splitting the pickup across two depots is a third leg nobody asked for.
        """
        wanted = [p for p in parts if p]
        return [
            w.id
            for w in self.warehouses.values()
            if all(w.stock.get(p, 0) > 0 for p in wanted)
        ]

    def claim_part(self, warehouse_id: str, part: str) -> bool:
        """Take one unit off a depot shelf. False means it had already gone.

        The same synchronous test-and-set as ``claim_technician``, and it exists for
        the same reason: ``create_work_order`` spends seconds on CAMARA Location
        Retrieval between reading stock and committing to a depot, and two overlapping
        investigations that both need the last alternator would otherwise both be told
        they had one. The failure is worse than the technician version, because it is
        invisible — two trucks arrive at the same depot and the second driver finds an
        empty shelf, having already made the journey.

        Callers must select a depot from ``stock_on_hand`` and claim it inside the same
        synchronous block, with no await in between.
        """
        wh = self.warehouses.get(warehouse_id)
        if wh is None or wh.stock.get(part, 0) <= 0:
            return False
        wh.stock[part] -= 1
        self.publish_warehouses()
        return True

    def release_part(self, warehouse_id: str, part: str) -> None:
        """Put a claimed unit back — the job it was reserved for never happened.

        Only for a dispatch that is abandoned before anyone drives anywhere (a stale
        epoch, a cancelled work order). A *completed* repair does not come back through
        here: that part was fitted to a machine and is gone. See ``_replenish``.
        """
        wh = self.warehouses.get(warehouse_id)
        if wh is None or not part:
            return
        wh.stock[part] = wh.stock.get(part, 0) + 1
        self.publish_warehouses()

    def _replenish(self, wo: WorkOrder) -> None:
        """Restock the part a finished job consumed.

        Physically the component is now bolted into a machine, so "restock" is the
        resupply that follows rather than the part coming back. Modelled as immediate
        because the alternative on a demo that runs for an hour is a depot that drains
        to nothing and a dispatcher that then has nothing to reason about — the
        interesting behaviour is the routing and the shortfall, not the lead time on a
        purchase order. A pilot would replace this with a real reorder cycle, and the
        reorder points in ``seed.PART_REORDER_AT`` are already the hook for it.
        """
        if not wo.warehouse_id:
            return
        wh = self.warehouses.get(wo.warehouse_id)
        if wh is None:
            return
        for part in wo.parts or ([wo.part] if wo.part else []):
            wh.stock[part] = wh.stock.get(part, 0) + 1
        self.publish_warehouses()

    def publish_warehouses(self) -> None:
        bus.publish(
            WsEvent(
                type="warehouses",
                payload={"warehouses": [w.model_dump(mode="json") for w in self.warehouses.values()]},
            )
        )

    def add_work_order(self, wo: WorkOrder) -> bool:
        """Put a dispatch on the board. False means it was refused as stale.

        The same epoch guard the rest of the investigation has, at the one write that
        was missing it. ``Tracer.check_current`` raises ``StaleInvestigation`` on the
        *next* step after a reset, and re-checks are epoch-stamped — but a dispatch
        spends ~3.6s inside ``create_work_order`` asking CAMARA Location Retrieval where
        each technician is, with no trace step in the middle. A presenter hitting Reset
        across that window got a clean fleet with a work order on it: WO-0001 against an
        incident that no longer existed, `dispatches_issued` reading 1 on an untouched
        site, and a card on the dashboard for a machine nobody had reported. The tracer
        then killed the rest of the investigation one step later, so the work order was
        also the only thing that survived — an order that could never be closed by the
        run that raised it.

        What dates the dispatch is the investigation's own task. Every trace step it
        narrates stamps that task with the epoch it is working in — the same instant
        ``Tracer.check_current`` last looked — and the last of those steps is the one
        announcing that the crew are being located, immediately before this gap. So a
        stamp that no longer matches means the fleet changed under a run that is still
        mid-dispatch. Deliberately not keyed on the incident: reset restarts the
        incident counter, so ``INC-0001`` names a different incident in every epoch and
        callers that mint their own ids collide with it. A task cannot be confused with
        another task. One that never narrated anything — the tools called directly from
        a test — carries no stamp and is not judged.

        No availability flip here, still on purpose. The technician was claimed by
        ``create_work_order`` the instant it chose them, before the work order existed;
        claiming again at this point would be a second source of truth for the same
        fact, and the one that arrives too late to prevent anything.
        """
        task = _current_task()
        dispatched_in = None if task is None else self._task_epoch.get(task)
        if dispatched_in is not None and dispatched_in != self.epoch:
            log.info(
                "dropping %s for %s (%s) — the investigation was reasoning about epoch %d "
                "and the fleet is on %d; reset while the dispatch was in flight",
                wo.id, wo.asset_id, wo.incident_id, dispatched_in, self.epoch,
            )
            return False
        self.work_orders[wo.id] = wo
        self.dispatches_issued += 1
        bus.publish(WsEvent(type="work_order", payload=wo.model_dump(mode="json")))
        return True

    def dispatch_in_flight(self, wo: WorkOrder) -> bool:
        """Is the investigation that raised this work order still finishing with it?

        A dispatch is not one write. The agent adds the work order, narrates one more
        trace step — 0.7s of deliberate pause so the reasoning is readable on stage —
        and only then marks the asset ``dispatched`` and closes the incident. The work
        order is visible on the dashboard for that whole window, so it can be cancelled
        or completed from the UI inside it, and that used to run straight through:
        ``delete_work_order`` released the technician and put the machine back to
        ``healthy``, then the investigation, still in flight, set the very same asset to
        ``dispatched`` and closed the incident against a work order that no longer
        existed. ``dispatched`` is a state the freshness sweep skips by design, so the
        machine sat there with nobody driving to it and no job to complete — invisible
        to the detector until somebody hit Reset.

        An open incident is exactly that window: the work order does not exist before
        ``create_work_order``, and the incident closes a step after it.
        """
        inc = self.incidents.get(wo.incident_id)
        return inc is not None and inc.closed_at is None

    def resume_telemetry(self, asset_id: str) -> None:
        """Put a machine we have judged healthy back into service.

        Deciding an asset is fine is only half the answer — the simulator is still
        withholding its heartbeat, so ``last_seen`` never advances and the detector
        opens a fresh incident on it seconds later. Clearing the scenario is what
        makes "no fault found" actually mean the machine came back.
        """
        from .simulator import simulator

        simulator.clear(asset_id)
        self.set_asset_state(asset_id, "healthy", last_seen=utcnow())

    def complete_work_order(self, wo: WorkOrder) -> None:
        """Finish a job: free the crew, put the machine back into service.

        The repair is what ends the scenario. Until the simulator is told the asset is
        fixed it keeps withholding telemetry, so ``last_seen`` never advances and the
        detector opens a fresh incident on a machine we just repaired — an endless
        dispatch loop on an idle dashboard.
        """
        from .simulator import simulator

        if wo.status == "completed":
            return
        wo.status = "completed"
        # The part went into the machine; the depot books a replacement in.
        self._replenish(wo)
        # A visit that serviced the machine restarts its service clock — including a
        # corrective or predictive visit that bundled the service in. Without this the
        # machine stays on the overdue board after the very trip that cleared it, and
        # an operator schedules the same work twice.
        if wo.maintenance_type == "preventive" or wo.bundled_service:
            asset_serviced = self.assets.get(wo.asset_id)
            if asset_serviced is not None:
                asset_serviced.hours_since_service = 0.0
        if wo.technician_id:
            tech = self.technicians.get(wo.technician_id)
            if tech:
                tech.available = True
                self.publish_technicians()
        # Repaired: the heartbeat resumes.
        simulator.clear(wo.asset_id)
        asset = self.assets.get(wo.asset_id)
        if asset and asset.state in ("dispatched", "silent", "anomaly"):
            self.set_asset_state(wo.asset_id, "healthy", last_seen=utcnow())
        bus.publish(WsEvent(type="work_order", payload=wo.model_dump(mode="json")))

    def close_no_fault_found(self, wo: WorkOrder) -> None:
        """The technician attended, found nothing to repair, and came back.

        A prediction can be wrong. When it is, the visit still happened and the truck
        still rolled, but nothing was fitted — so this is not a completed repair and
        must not be recorded as one. Three things follow, and they are the reason this
        is a separate path rather than a flag on ``complete_work_order``:

        * **The parts go back on the shelf, not through resupply.** A completed repair
          consumes its part and the depot books a replacement in (``_replenish``); an
          unfitted part is still an unfitted part and returns to the depot it was
          collected from, at the same count. Running it through the completion path
          would quietly conjure a spare component out of a wasted journey.
        * **The machine returns to service healthy**, because it always was.
        * **It is counted.** ``no_fault_found`` sits next to ``false_dispatches_avoided``
          on the dashboard on purpose. A product whose pitch is "we stop you driving to
          machines that are fine" has no business hiding it when it does exactly that.

        The incident is deliberately left as the agent closed it. Rewriting it to say
        no fault would erase what the system actually concluded and make the trace
        disagree with the record it produced. The work order carries the correction.
        """
        from .simulator import simulator

        if wo.status == "completed":
            return
        wo.status = "completed"
        wo.no_fault_found = True
        # Back to the depot it came from, uncounted against stock.
        for part in wo.parts or ([wo.part] if wo.part else []):
            self.release_part(wo.warehouse_id, part)
        if wo.technician_id:
            tech = self.technicians.get(wo.technician_id)
            if tech:
                tech.available = True
                self.publish_technicians()
        self.no_fault_found += 1
        simulator.clear(wo.asset_id)
        asset = self.assets.get(wo.asset_id)
        if asset and asset.state in ("dispatched", "silent", "anomaly"):
            self.set_asset_state(wo.asset_id, "healthy", last_seen=utcnow())
        bus.publish(WsEvent(type="work_order", payload=wo.model_dump(mode="json")))

    def delete_work_order(self, wo: WorkOrder) -> None:
        """Drop a job entirely.

        Cancelling still releases the technician and the machine — an operator who
        dismisses a work order has decided nobody is going, not that the asset should
        stay stuck in a dispatched state forever.
        """
        from .simulator import simulator

        self.work_orders.pop(wo.id, None)
        if wo.status != "completed":
            # Nobody fitted them, so they go back on the shelf rather than being
            # written off — the mirror of releasing the technician immediately below.
            for part in wo.parts or ([wo.part] if wo.part else []):
                self.release_part(wo.warehouse_id, part)
            if wo.technician_id:
                tech = self.technicians.get(wo.technician_id)
                if tech:
                    tech.available = True
                    self.publish_technicians()
            simulator.clear(wo.asset_id)
            asset = self.assets.get(wo.asset_id)
            if asset and asset.state in ("dispatched", "silent", "anomaly"):
                self.set_asset_state(wo.asset_id, "healthy", last_seen=utcnow())
        bus.publish(WsEvent(type="work_order_deleted", payload={"id": wo.id}))

    def advance_work_orders(self) -> None:
        """Let dispatched jobs finish on their own.

        A fleet that only ever loses technicians is not a fleet. Completing jobs frees
        the crew, returns the machine to service, and lets the demo run indefinitely
        instead of degrading into work orders with nobody assigned.

        Deliberately not gated on ``dispatch_in_flight`` the way the operator's buttons
        are. The timer only touches a job that has been sitting for
        ``work_order_complete_seconds`` — ninety, against a settling window under a
        second — so it cannot land inside it, and it is the one thing that eventually
        frees an order whose investigation died between the work order and the incident
        close. Refusing here would turn that crash into a permanently stuck job and a
        technician who never comes back.
        """
        from .config import get_settings

        after = get_settings().work_order_complete_seconds
        now = utcnow()
        for wo in list(self.work_orders.values()):
            if wo.status == "completed":
                continue
            # Nobody is driving to this one — it is waiting on a free technician or on
            # a part no depot holds. Completing it on a timer would mark a machine
            # repaired that no one has visited, free a technician who was never
            # assigned, and return the asset to service still broken. The waiting job
            # is picked up by the re-investigation sweep instead, which is the path
            # that actually assigns somebody.
            if wo.technician_id is None:
                continue
            if (now - wo.created_at).total_seconds() < after:
                continue
            self.complete_work_order(wo)

    def raise_geofence_alert(self, ev) -> GeofenceAlert | None:
        """Warn that a working machine is leaving the site.

        Counted as a prevented incident rather than an avoided dispatch, because
        nothing has gone wrong yet — that is the distinction worth keeping. An
        avoided dispatch means we correctly declined to act on a failure; this means
        there was no failure to act on, because somebody was told in time.
        """
        asset = self.assets.get(ev.asset_id)
        if asset is None:
            return None
        if ev.event_type == "area-entered":
            asset.offsite = False
            bus.publish(WsEvent(type="asset_update", payload=asset.model_dump(mode="json")))
            return None

        asset.offsite = True
        alert = GeofenceAlert(
            id=f"GF-{next(self._gf_seq):04d}",
            asset_id=ev.asset_id,
            asset_label=asset.label,
            latitude=ev.latitude,
            longitude=ev.longitude,
            distance_km=ev.distance_km,
            source=ev.source,
        )
        self.geofence_alerts[alert.id] = alert
        self.incidents_prevented += 1
        if len(self.geofence_alerts) > 50:
            keep = sorted(self.geofence_alerts.values(), key=lambda a: a.at)[-50:]
            self.geofence_alerts = {a.id: a for a in keep}
        bus.publish(WsEvent(type="asset_update", payload=asset.model_dump(mode="json")))
        bus.publish(WsEvent(type="geofence_alert", payload=alert.model_dump(mode="json")))
        return alert

    def record_blindspot_avoided(self) -> None:
        self.false_dispatches_avoided += 1

    # ── KPIs ──────────────────────────────────────────────────────────────
    def kpis(self) -> Kpis:
        fleet = list(self.assets.values())
        available = sum(1 for a in fleet if a.state in ("healthy", "anomaly", "blindspot"))
        open_incidents = sum(1 for i in self.incidents.values() if i.closed_at is None)
        avg_triage = (
            sum(self._triage_durations) / len(self._triage_durations)
            if self._triage_durations
            else 0.0
        )
        return Kpis(
            fleet_size=len(fleet),
            available_assets=available,
            fleet_availability_pct=round(100.0 * available / len(fleet), 1) if fleet else 100.0,
            open_incidents=open_incidents,
            false_dispatches_avoided=self.false_dispatches_avoided,
            incidents_prevented=self.incidents_prevented,
            dispatches_issued=self.dispatches_issued,
            no_fault_found=self.no_fault_found,
            avg_triage_seconds=round(avg_triage, 1),
        )

    def publish_kpis(self) -> None:
        bus.publish(WsEvent(type="kpis", payload=self.kpis().model_dump(mode="json")))

    def publish_positions(self, asset_ids: list[str]) -> None:
        """Push moved assets to the map.

        Technicians were published every tick and assets were not, so the machines sat
        frozen wherever the initial snapshot put them: `TelemetrySample` carries no
        coordinates, and the only `asset_update` publishers were a state change and a
        geofence crossing. A machine driving off site therefore did not move at all for
        half a minute and then jumped the whole way in one frame, when the crossing
        fired — while the narrator described it driving.
        """
        for asset_id in asset_ids:
            asset = self.assets.get(asset_id)
            if asset is not None:
                bus.publish(
                    WsEvent(type="asset_update", payload=asset.model_dump(mode="json"))
                )

    def publish_technicians(self) -> None:
        """Crews move and go on and off shift; the map has to see it.

        Without this the dashboard only ever knows where the crew were when it
        connected, which makes the network-located dispatch look like it picked
        someone at random.
        """
        bus.publish(
            WsEvent(
                type="technicians",
                payload={"technicians": [t.model_dump(mode="json") for t in self.technicians.values()]},
            )
        )

    # ── snapshot for a freshly-connected dashboard ───────────────────────
    def snapshot(self) -> dict:
        return {
            "assets": [a.model_dump(mode="json") for a in self.assets.values()],
            "technicians": [t.model_dump(mode="json") for t in self.technicians.values()],
            "warehouses": [w.model_dump(mode="json") for w in self.warehouses.values()],
            "incidents": [i.model_dump(mode="json") for i in self.incidents.values()],
            "trace": {k: [s.model_dump(mode="json") for s in v] for k, v in self.trace.items()},
            "work_orders": [w.model_dump(mode="json") for w in self.work_orders.values()],
            "geofence_alerts": [
                a.model_dump(mode="json") for a in self.geofence_alerts.values()
            ],
            "latest_telemetry": {
                k: v.model_dump(mode="json") for k, v in self.latest_telemetry.items()
            },
            "kpis": self.kpis().model_dump(mode="json"),
            "dead_zones": _dead_zones(),
        }


store = Store()
