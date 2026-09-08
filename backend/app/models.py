"""Pydantic domain models shared across the backend and streamed to the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── The three maintenance types ─────────────────────────────────────────────
#
# Industry terminology, and the distinction is not cosmetic — it is *what triggered
# the work*, which is the thing an operations manager plans and budgets against:
#
#   corrective  the machine already failed. Reactive, unplanned, and the expensive
#               one — this is the path an incident takes when the agent confirms a
#               genuine fault.
#   preventive  nothing is wrong; the service interval came due. Calendar- and
#               usage-driven, scheduled in advance, and the cheapest of the three.
#   predictive  nothing has failed *yet*, but the forecast model expects it to. The
#               work is scheduled off a condition signal rather than a clock.
#
# The system produces all three, so every work order says which one it is rather than
# leaving an operator to infer it from whether an incident happens to be attached.
MaintenanceType = Literal["corrective", "preventive", "predictive"]


# ── Assets & telemetry ──────────────────────────────────────────────────────

AssetKind = Literal["excavator", "dozer", "haul_truck", "crane", "grader", "loader"]

AssetState = Literal[
    "healthy",       # streaming, nominal
    "anomaly",       # telemetry looks off but still reporting
    "silent",        # heartbeat lost — incident open, agent investigating
    "blindspot",     # confirmed cellular coverage gap — no dispatch
    "dispatched",    # confirmed hardware fault — technician en route
]


class Asset(BaseModel):
    id: str                       # e.g. "EQ-0007"
    kind: AssetKind
    label: str                    # human name, e.g. "Excavator EX-07"
    site: str                     # e.g. "NEOM — The Line, Sector 3"
    latitude: float
    longitude: float
    state: AssetState = "healthy"
    # Outside the site perimeter. Not a state: the machine is still healthy and still
    # reporting, which is exactly why catching it here is worth anything.
    offsite: bool = False
    last_seen: datetime = Field(default_factory=utcnow)
    # ── preventive servicing ────────────────────────────────────────────────
    # Hours on the machine, and hours since it was last serviced. Preventive work is
    # scheduled off these and nothing else: no telemetry, no model, just a clock that
    # every fleet already runs. Kept on the asset rather than in a side table because
    # every consumer of an asset — the map, the fleet table, the planner — wants to
    # know whether it is due, and a join for that is a join everyone forgets.
    engine_hours: float = 0.0
    service_interval_hours: float = 500.0
    hours_since_service: float = 0.0

    @property
    def service_due_in_hours(self) -> float:
        """Negative means overdue. The sign is the whole answer, so it is not clamped."""
        return self.service_interval_hours - self.hours_since_service

    @property
    def service_overdue(self) -> bool:
        return self.service_due_in_hours <= 0


class TelemetrySample(BaseModel):
    asset_id: str
    ts: datetime = Field(default_factory=utcnow)
    reachable: bool = True
    telemetry_age_sec: float = 0.0
    signal_strength_dbm: float = -60.0
    neighbor_fail_count: int = 0
    engine_temp_c: float = 82.0


# ── Incidents ───────────────────────────────────────────────────────────────

IncidentStatus = Literal[
    "open",
    "investigating",
    "network_blindspot",     # coverage gap — no dispatch
    "no_fault",              # network fine, but the machine reads healthy — no dispatch
    "roaming_blocked",       # on a foreign network — connectivity ticket, no dispatch
    # Two dispatches, not one. A failed reporting sensor on a healthy machine costs a
    # cheap kit; a broken machine costs a mechanic and a heavy component. Recording both
    # as "hardware" is what made the graded response invisible in the incident record.
    "sensor_confirmed",      # reporting sensor failed — technician with a sensor kit
    "hardware_confirmed",    # real fault — mechanic dispatched with the named part
    # Diagnosed, part named, work order raised — and every technician is already on a
    # job. Deliberately not folded into the two dispatch statuses above: nobody is en
    # route, and an incident that reads "dispatched" when no one is driving anywhere is
    # the one lie this system cannot afford to tell an operator.
    "awaiting_crew",
    # Diagnosed and crewed, but no depot on site holds the component. Distinct from
    # awaiting_crew for the same reason that one is distinct from "dispatched": the
    # blocker is different, and so is the person who can clear it. A missing crew is a
    # scheduling problem; a missing part is a purchasing one.
    "awaiting_part",
]


class Incident(BaseModel):
    id: str
    asset_id: str
    opened_at: datetime = Field(default_factory=utcnow)
    closed_at: datetime | None = None
    status: IncidentStatus = "open"
    summary: str = ""
    resolution: str = ""


# ── Agent reasoning trace ───────────────────────────────────────────────────


class TraceStep(BaseModel):
    incident_id: str
    ts: datetime = Field(default_factory=utcnow)
    step: int
    thought: str
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    observation: str = ""


# ── Fault prediction (ML) ───────────────────────────────────────────────────


class FaultPrediction(BaseModel):
    asset_id: str
    mode: Literal["NORMAL", "NETWORK_OUTAGE", "DEVICE_FAILURE", "SENSOR_FAILURE"]
    confidence: float
    probabilities: dict[str, float] = Field(default_factory=dict)
    recommended_part: str = ""
    # Which component the history says is failing, and how sure. "Hardware fault"
    # does not fill a van; naming the part is what makes it a first-time fix.
    component: str = ""
    component_confidence: float = 0.0
    rationale: str = ""


# ── Work orders & technicians ───────────────────────────────────────────────


class Technician(BaseModel):
    """A crew member — and, for our purposes, a phone on the same network.

    Their position is not something we are told; it is something we ask the operator
    for, exactly as we do for a silent machine. One API answers both halves of the
    dispatch question: where is the broken asset, and who is actually nearest to it.
    """

    id: str
    name: str
    latitude: float
    longitude: float
    available: bool = True
    # What actually rides in the van, which is only ever consumables and the telemetry
    # sensor kit. The four failing components this system names — a hydraulic pump, a
    # radiator core, a bearing set, an alternator — are pallet-scale items that live in
    # a depot and get loaded by forklift. Modelling them as van stock was the thing a
    # field-service reviewer spotted immediately: it silently assumed six technicians
    # each driving a warehouse around a construction site.
    parts_on_hand: list[str] = Field(default_factory=list)
    # Where the position came from the last time we asked.
    located_via: Literal["live", "mock", "seed"] = "seed"


class Warehouse(BaseModel):
    """A parts depot: a fixed building on the site with stock on its shelves.

    Two of them, deliberately. With one depot every technician detours through the
    same point, so the pickup adds a constant to everybody's journey and never
    re-orders the crew — the routing would be theatre. With two, the fastest responder
    genuinely stops being the nearest one, which is the decision this models.
    """

    id: str
    name: str
    latitude: float
    longitude: float
    # Part number → units on the shelf. A part absent from the dict is a part this
    # depot does not carry at all, which is a different statement from carrying zero
    # of it — one is "wrong depot", the other is "reorder".
    stock: dict[str, int] = Field(default_factory=dict)


# "queued" is a job with no technician on it: the fault is confirmed and the part is
# named, but the whole crew is already out. It is a distinct status rather than
# "created" with an empty name because a card that says "assigned" or "dispatched"
# with a blank technician and a 0-minute ETA is a promise nobody is keeping.
WorkOrderStatus = Literal["queued", "awaiting_part", "created", "assigned", "completed"]


class GeofenceAlert(BaseModel):
    """A machine left the site while it was still working fine.

    Deliberately not an Incident. An incident means something already went wrong and
    needs diagnosing; this is the opposite — nothing has failed, the machine is still
    reporting, and the point is to reach the operator while that is still true.
    """

    id: str
    asset_id: str
    asset_label: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    distance_km: float = 0.0
    at: datetime = Field(default_factory=utcnow)
    source: str = "mock"


class WorkOrder(BaseModel):
    id: str
    # Empty for preventive and predictive work: nothing failed, so no incident was
    # ever opened. Only corrective jobs trace back to one.
    incident_id: str = ""
    asset_id: str
    created_at: datetime = Field(default_factory=utcnow)
    status: WorkOrderStatus = "created"
    # What triggered this job. See MaintenanceType — an operator plans corrective,
    # preventive and predictive work differently, so the record says which it is.
    maintenance_type: MaintenanceType = "corrective"
    fault_mode: str = ""
    component: str = ""
    # Two models, two numbers: `confidence` is the classifier's confidence in the
    # fault mode, `component_confidence` the prognostic model's confidence in the
    # part it named. Carry both so the card never has to pass one off as the other.
    confidence: float = 0.0
    component_confidence: float = 0.0
    part: str = ""
    # Everything that has to be on the truck for this visit. ``part`` stays the
    # headline item the card leads with; this is what stock is actually claimed
    # against, because a bundled visit collects a component *and* a service kit and
    # releasing only one of them on a cancellation leaks the other off the shelf.
    parts: list[str] = Field(default_factory=list)
    # The technician attended and found nothing to repair. Field service calls this
    # "no fault found", and it is the exact trip this whole system exists to prevent
    # (see docs/EVIDENCE.md), so when one happens anyway it is recorded rather than
    # closed as an ordinary repair. Nothing was fitted, so the parts go back.
    no_fault_found: bool = False
    # This visit also clears the machine's scheduled service. Only ever true when the
    # forecast and the service clock landed on the same machine — the one case where
    # two separate journeys collapse into one.
    bundled_service: bool = False
    asset_latitude: float = 0.0
    asset_longitude: float = 0.0
    technician_id: str | None = None
    technician_name: str = ""
    # Whether the crew position that produced this assignment was network-verified.
    technician_located_via: str = "seed"
    # ── the route ───────────────────────────────────────────────────────────
    # A heavy component means the journey is technician → depot → machine, so a single
    # distance cannot describe it. Both legs are carried separately because the map
    # draws them separately and because the two numbers are what make a longer-distance
    # assignment legible as the faster one.
    warehouse_id: str = ""
    warehouse_name: str = ""
    leg_to_warehouse_km: float = 0.0
    leg_to_asset_km: float = 0.0
    # Time on the ground at the depot: finding the part, booking it out, loading it.
    # Zero when nothing has to be collected.
    loading_minutes: int = 0
    # A technician who was closer to the machine but slower to reach it, because of
    # where the part was. Recorded so a dispatch that drives past a nearer person
    # explains itself instead of looking like a bug on a map — the same reason the
    # part-carrying version of this field existed, measured in the unit that now
    # decides it.
    nearest_skipped_name: str = ""
    nearest_skipped_km: float = 0.0
    nearest_skipped_minutes_later: int = 0
    # Total driven distance across both legs — what the fuel and the map care about.
    distance_km: float = 0.0
    eta_minutes: int = 0


# ── KPIs ────────────────────────────────────────────────────────────────────


class Kpis(BaseModel):
    fleet_size: int = 0
    available_assets: int = 0
    fleet_availability_pct: float = 100.0
    open_incidents: int = 0
    false_dispatches_avoided: int = 0
    # Machines caught leaving the site while still healthy. Distinct from an avoided
    # dispatch: nothing failed, because somebody was warned in time.
    incidents_prevented: int = 0
    dispatches_issued: int = 0
    # Dispatches that arrived and found nothing wrong. The honest counterpart to
    # false_dispatches_avoided: this system is sold on cutting these, so it reports
    # its own rather than only counting the ones it stopped.
    no_fault_found: int = 0
    avg_triage_seconds: float = 0.0


# ── WebSocket envelope ──────────────────────────────────────────────────────

EventType = Literal[
    "snapshot",       # full state, sent on connect
    "telemetry",
    "asset_update",
    "incident_update",
    "trace_step",
    "work_order",
    "work_order_deleted",
    "geofence_alert",
    "technicians",
    "warehouses",
    "kpis",
    "dead_zones",
]


class WsEvent(BaseModel):
    type: EventType
    payload: dict[str, Any]
    ts: datetime = Field(default_factory=utcnow)
