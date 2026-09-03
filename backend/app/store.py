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
        self.latest_telemetry: dict[str, TelemetrySample] = {}
        self._incident_seq = itertools.count(1)
        self._wo_seq = itertools.count(1)
        # KPI counters that persist across the session
        self.false_dispatches_avoided = 0
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
        self.latest_telemetry.clear()
        self._incident_seq = itertools.count(1)
        self._wo_seq = itertools.count(1)
        self.false_dispatches_avoided = 0
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
        bus.publish(WsEvent(type="work_order", payload=wo.model_dump(mode="json")))

    def advance_work_orders(self) -> None:
        """Let dispatched jobs finish.

        A fleet that only ever loses technicians is not a fleet. Completing jobs frees
        the crew, returns the machine to service, and lets the demo run indefinitely
        instead of degrading into work orders with nobody assigned.
        """
        from .config import get_settings

        after = get_settings().work_order_complete_seconds
        now = utcnow()
        for wo in self.work_orders.values():
            if wo.status == "completed":
                continue
            if (now - wo.created_at).total_seconds() < after:
                continue
            wo.status = "completed"
            if wo.technician_id:
                tech = self.technicians.get(wo.technician_id)
                if tech:
                    tech.available = True
            asset = self.assets.get(wo.asset_id)
            if asset and asset.state == "dispatched":
                self.set_asset_state(wo.asset_id, "healthy", last_seen=now)
            bus.publish(WsEvent(type="work_order", payload=wo.model_dump(mode="json")))

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
            dispatches_issued=self.dispatches_issued,
            avg_triage_seconds=round(avg_triage, 1),
        )

    def publish_kpis(self) -> None:
        bus.publish(WsEvent(type="kpis", payload=self.kpis().model_dump(mode="json")))

    # ── snapshot for a freshly-connected dashboard ───────────────────────
    def snapshot(self) -> dict:
        return {
            "assets": [a.model_dump(mode="json") for a in self.assets.values()],
            "technicians": [t.model_dump(mode="json") for t in self.technicians.values()],
            "incidents": [i.model_dump(mode="json") for i in self.incidents.values()],
            "trace": {k: [s.model_dump(mode="json") for s in v] for k, v in self.trace.items()},
            "work_orders": [w.model_dump(mode="json") for w in self.work_orders.values()],
            "latest_telemetry": {
                k: v.model_dump(mode="json") for k, v in self.latest_telemetry.items()
            },
            "kpis": self.kpis().model_dump(mode="json"),
            "dead_zones": _dead_zones(),
        }


store = Store()
