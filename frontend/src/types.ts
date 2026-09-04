// Mirrors backend/app/models.py

export type AssetState =
  | "healthy"
  | "anomaly"
  | "silent"
  | "blindspot"
  | "dispatched";

export interface Asset {
  id: string;
  kind: string;
  label: string;
  site: string;
  latitude: number;
  longitude: number;
  state: AssetState;
  last_seen: string;
  // Outside the site perimeter. Not a state — the machine is still healthy and
  // still reporting, which is the entire reason catching it here is worth anything.
  offsite?: boolean;
}

export interface Technician {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  available: boolean;
  parts_on_hand: string[];
  located_via: string;
}

export interface TelemetrySample {
  asset_id: string;
  ts: string;
  reachable: boolean;
  telemetry_age_sec: number;
  signal_strength_dbm: number;
  neighbor_fail_count: number;
  engine_temp_c: number;
  ground_truth: string | null;
}

export type IncidentStatus =
  | "open"
  | "investigating"
  | "network_blindspot"
  | "no_fault"
  | "roaming_blocked"
  | "hardware_confirmed"
  | "closed";

export interface Incident {
  id: string;
  asset_id: string;
  opened_at: string;
  closed_at: string | null;
  status: IncidentStatus;
  summary: string;
  resolution: string;
}

export interface TraceStep {
  incident_id: string;
  ts: string;
  step: number;
  thought: string;
  tool: string | null;
  args: Record<string, unknown>;
  observation: string;
}

export interface WorkOrder {
  id: string;
  incident_id: string;
  asset_id: string;
  created_at: string;
  status: string;
  fault_mode: string;
  component: string;
  confidence: number;
  part: string;
  asset_latitude: number;
  asset_longitude: number;
  technician_id: string | null;
  technician_name: string;
  distance_km: number;
  eta_minutes: number;
  technician_located_via: string;
  nearest_skipped_name: string;
  nearest_skipped_km: number;
}

export interface GeofenceAlert {
  id: string;
  asset_id: string;
  asset_label: string;
  latitude: number;
  longitude: number;
  distance_km: number;
  at: string;
  source: string;
  acknowledged: boolean;
}

export interface Kpis {
  fleet_size: number;
  available_assets: number;
  fleet_availability_pct: number;
  open_incidents: number;
  false_dispatches_avoided: number;
  incidents_prevented: number;
  dispatches_issued: number;
  avg_triage_seconds: number;
}

/** A patch of ground the agent has learned swallows signal. */
export interface DeadZone {
  latitude: number;
  longitude: number;
  span: number;
  incidents: number;
  last_seen: string;
}

export type WsEventType =
  | "snapshot"
  | "telemetry"
  | "asset_update"
  | "incident_update"
  | "trace_step"
  | "work_order"
  | "work_order_deleted"
  | "geofence_alert"
  | "technicians"
  | "kpis"
  | "dead_zones";

export interface WsEvent {
  type: WsEventType;
  payload: any;
  ts: string;
}

/** A forecast, not a status. An asset can be streaming perfectly and still be
 *  days from a bearing failure — that gap is the whole point of the model. */
export interface RiskRow {
  asset_id: string;
  label?: string;
  site?: string;
  risk: number;
  horizon_hours: number | null;
  at_risk: boolean;
  vibration_mm_s: number;
  vibration_delta: number;
  oil_particle_count: number;
  oil_particle_delta: number;
}
