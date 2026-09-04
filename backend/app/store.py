"""In-memory application state for the prototype.

Single-process, single-writer (the asyncio event loop). No database — the demo
starts from a clean, deterministic seed every time. Every mutation publishes a
``WsEvent`` so connected dashboards stay in sync.
"""

from __future__ import annotations

import itertools
from datetime import datetime

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
    WorkOrder,
    WsEvent,
    utcnow,
)
from .seed import build_demo_fleet, build_technicians


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
        self.incidents: dict[str, Incident] = {}
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
        self._triage_durations: list[float] = []
        self.reset()

    # ── lifecycle ──────────────────────────────────────────────────────────
    def reset(self) -> None:
        self.epoch += 1
        self.assets = {a.id: a for a in build_demo_fleet()}
        self.technicians = {t.id: t for t in build_technicians()}
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
        self.trace.setdefault(step.incident_id, []).append(step)
        bus.publish(WsEvent(type="trace_step", payload=step.model_dump(mode="json")))

    # ── work orders ───────────────────────────────────────────────────────
    def next_work_order_id(self) -> str:
        return f"WO-{next(self._wo_seq):04d}"

    def add_work_order(self, wo: WorkOrder) -> None:
        self.work_orders[wo.id] = wo
        self.dispatches_issued += 1
        if wo.technician_id:
            tech = self.technicians.get(wo.technician_id)
            if tech:
                tech.available = False
                self.publish_technicians()
        bus.publish(WsEvent(type="work_order", payload=wo.model_dump(mode="json")))

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

    def delete_work_order(self, wo: WorkOrder) -> None:
        """Drop a job entirely.

        Cancelling still releases the technician and the machine — an operator who
        dismisses a work order has decided nobody is going, not that the asset should
        stay stuck in a dispatched state forever.
        """
        from .simulator import simulator

        self.work_orders.pop(wo.id, None)
        if wo.status != "completed":
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
        """
        from .config import get_settings

        after = get_settings().work_order_complete_seconds
        now = utcnow()
        for wo in list(self.work_orders.values()):
            if wo.status == "completed":
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
            avg_triage_seconds=round(avg_triage, 1),
        )

    def publish_kpis(self) -> None:
        bus.publish(WsEvent(type="kpis", payload=self.kpis().model_dump(mode="json")))

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
