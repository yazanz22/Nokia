import type { WorkOrder } from "../types";

export function WorkOrderCard({ wo }: { wo: WorkOrder }) {
  return (
    <div className="wo">
      <div className="wo-top">
        <span className="wo-id">{wo.id}</span>
        <span className="wo-fault">
          {wo.fault_mode.replace("_", " ")}
          <br />
          {(wo.confidence * 100).toFixed(0)}% confidence
        </span>
      </div>

      <dl className="wo-grid">
        <dt>Asset</dt>
        <dd>{wo.asset_id}</dd>
        <dt>Part</dt>
        <dd>{wo.part || "—"}</dd>
        <dt>Technician</dt>
        <dd>{wo.technician_name || "unassigned"}</dd>
        <dt>Position</dt>
        <dd>
          {wo.asset_latitude.toFixed(4)}, {wo.asset_longitude.toFixed(4)}
        </dd>
      </dl>

      <div className="wo-eta">
        <span className="big">{wo.eta_minutes}</span>
        <span className="lbl">min out</span>
        <span style={{ flex: 1 }} />
        <span className="big" style={{ fontSize: 16 }}>
          {wo.distance_km.toFixed(1)}
        </span>
        <span className="lbl">km</span>
      </div>
    </div>
  );
}
