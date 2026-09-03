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

export interface Kpis {
  fleet_size: number;
  available_assets: number;
  fleet_availability_pct: number;
  open_incidents: number;
  false_dispatches_avoided: number;
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
  | "technicians"
  | "kpis"
  | "dead_zones";

export interface WsEvent {
  type: WsEventType;
  payload: any;
  ts: string;
}
