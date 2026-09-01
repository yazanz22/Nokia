"""Pydantic domain models shared across the backend and streamed to the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    last_seen: datetime = Field(default_factory=utcnow)


class TelemetrySample(BaseModel):
    asset_id: str
    ts: datetime = Field(default_factory=utcnow)
    reachable: bool = True
    telemetry_age_sec: float = 0.0
    signal_strength_dbm: float = -60.0
    neighbor_fail_count: int = 0
    engine_temp_c: float = 82.0
    # true label from the dataset row this sample was drawn from — for the
    # simulator/demo only; the agent never sees it.
    ground_truth: str | None = None


# ── Incidents ───────────────────────────────────────────────────────────────

IncidentStatus = Literal[
    "open",
    "investigating",
    "network_blindspot",     # coverage gap — no dispatch
    "no_fault",              # network fine, but the machine reads healthy — no dispatch
    "hardware_confirmed",    # real fault — technician dispatched
    "closed",
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
    lead_days: int = 0
    rationale: str = ""


# ── Work orders & technicians ───────────────────────────────────────────────


class Technician(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    available: bool = True
    parts_on_hand: list[str] = Field(default_factory=list)


WorkOrderStatus = Literal["created", "assigned", "en_route", "completed"]


class WorkOrder(BaseModel):
    id: str
    incident_id: str
    asset_id: str
    created_at: datetime = Field(default_factory=utcnow)
    status: WorkOrderStatus = "created"
    fault_mode: str = ""
    confidence: float = 0.0
    part: str = ""
    asset_latitude: float = 0.0
    asset_longitude: float = 0.0
    technician_id: str | None = None
    technician_name: str = ""
    distance_km: float = 0.0
    eta_minutes: int = 0


# ── KPIs ────────────────────────────────────────────────────────────────────


class Kpis(BaseModel):
    fleet_size: int = 0
    available_assets: int = 0
    fleet_availability_pct: float = 100.0
    open_incidents: int = 0
    false_dispatches_avoided: int = 0
    dispatches_issued: int = 0
    avg_triage_seconds: float = 0.0


# ── WebSocket envelope ──────────────────────────────────────────────────────

EventType = Literal[
    "snapshot",       # full state, sent on connect
    "telemetry",
    "asset_update",
    "incident_update",
    "trace_step",
    "work_order",
    "kpis",
]


class WsEvent(BaseModel):
    type: EventType
    payload: dict[str, Any]
    ts: datetime = Field(default_factory=utcnow)
