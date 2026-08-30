import type { WorkOrder } from "../types";

export function WorkOrderCard({ wo }: { wo: WorkOrder }) {
  return (
    <div className="wo">
      <div className="top">
        <strong>{wo.id}</strong>
        <span className="fault">
          {wo.fault_mode} · {(wo.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <dl>
        <dt>Asset</dt>
        <dd>{wo.asset_id}</dd>
        <dt>Part</dt>
        <dd>{wo.part || "—"}</dd>
        <dt>Technician</dt>
        <dd>{wo.technician_name || "unassigned"}</dd>
        <dt>Distance</dt>
        <dd>{wo.distance_km.toFixed(1)} km</dd>
        <dt>ETA</dt>
        <dd>{wo.eta_minutes} min</dd>
        <dt>Location</dt>
        <dd>
          {wo.asset_latitude.toFixed(4)}, {wo.asset_longitude.toFixed(4)}
        </dd>
      </dl>
    </div>
  );
}
