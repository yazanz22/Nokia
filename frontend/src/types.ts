// Mirrors backend/app/models.py

export type AssetState =
  | "healthy"
  | "anomaly"
  | "silent"
  | "blindspot"
  | "dispatched";

export type MaintenanceType = "corrective" | "preventive" | "predictive";

export interface Asset {
  id: string;
  kind: string;
  label: string;
  site: string;
  latitude: number;
  longitude: number;
  state: AssetState;
  last_seen: string;
  // Preventive servicing runs off these two and nothing else.
  engine_hours: number;
  service_interval_hours: number;
  hours_since_service: number;
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
  // Van stock only. Components live in depots.
  parts_on_hand: string[];
  located_via: string;
}

export interface Warehouse {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  stock: Record<string, number>;
}

export interface StockRow {
  part: string;
  label: string;
  units: number;
  reorder_at: number;
  low: boolean;
  out: boolean;
}

export interface DepotStock {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  parts: StockRow[];
  low_count: number;
}

export interface ServiceRow {
  asset_id: string;
  label: string;
  site: string;
  engine_hours: number;
  service_interval_hours: number;
  hours_since_service: number;
  due_in_hours: number;
  state: "overdue" | "due_soon" | "ok";
  part: string;
}

export interface BundleRow extends ServiceRow {
  component: string;
  component_confidence: number;
  component_part: string;
  depot: string;
  horizon_hours: number | null;
  risk: number;
  already_scheduled: boolean;
}

export interface TelemetrySample {
  asset_id: string;
  ts: string;
  reachable: boolean;
  telemetry_age_sec: number;
  signal_strength_dbm: number;
  neighbor_fail_count: number;
  engine_temp_c: number;
}

export type IncidentStatus =
  | "open"
  | "investigating"
  | "network_blindspot"
  | "no_fault"
  | "roaming_blocked"
  | "sensor_confirmed"
  | "hardware_confirmed"
  // Diagnosed, part named, work order raised — and every technician is already out.
  // Kept apart from the two dispatch statuses on purpose: nobody is en route, and a
  // feed that reads "dispatched" while no one is driving anywhere is the one thing
  // this dashboard must never tell an operator.
  | "awaiting_crew"
  // Diagnosed and crewed, but no depot on site holds the component. A different
  // blocker from awaiting_crew, and a different person clears it: a missing crew is
  // a scheduling problem, a missing part is a purchasing one.
  | "awaiting_part"
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
  // What triggered the job. Corrective jobs come from an incident; the other two are
  // scheduled and carry no incident at all.
  maintenance_type: MaintenanceType;
  fault_mode: string;
  component: string;
  // Two models, two numbers. `confidence` is the fault-mode classifier's; this one is
  // the component model's. They sit next to each other on the card, so the card labels
  // which is which — an unlabelled percentage beside a part name gets read as the part's.
  confidence: number;
  component_confidence: number;
  part: string;
  parts: string[];
  bundled_service: boolean;
  // The technician attended and found nothing to repair. Not a completed repair:
  // nothing was fitted and the parts went back to the depot.
  no_fault_found: boolean;
  asset_latitude: number;
  asset_longitude: number;
  technician_id: string | null;
  technician_name: string;
  distance_km: number;
  eta_minutes: number;
  technician_located_via: string;
  // The depot leg. Empty warehouse_id means the part rode in the van and the run was
  // direct, which is why both legs are carried rather than one total distance.
  warehouse_id: string;
  warehouse_name: string;
  leg_to_warehouse_km: number;
  leg_to_asset_km: number;
  loading_minutes: number;
  nearest_skipped_name: string;
  nearest_skipped_km: number;
  nearest_skipped_minutes_later: number;
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
}

export interface Kpis {
  fleet_size: number;
  available_assets: number;
  fleet_availability_pct: number;
  open_incidents: number;
  false_dispatches_avoided: number;
  incidents_prevented: number;
  dispatches_issued: number;
  no_fault_found: number;
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
  | "warehouses"
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
  engine_temp_c?: number;
  hydraulic_pressure_bar?: number;
}
