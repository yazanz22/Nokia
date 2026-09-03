import { useState } from "react";
import { completeWorkOrder, deleteWorkOrder } from "../lib/api";
import type { WorkOrder } from "../types";

export function WorkOrderCard({ wo }: { wo: WorkOrder }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const done = wo.status === "completed";

  // The list is driven by the websocket, so there is nothing to update locally —
  // just guard against a double-click while the request is in flight.
  const act = async (fn: (id: string) => Promise<unknown>) => {
    setBusy(true);
    setErr("");
    try {
      await fn(wo.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className={`wo${done ? " wo-done" : ""}`}>
      <div className="wo-top">
        <span className="wo-id">
          {wo.id}
          <span className={`wo-status ${done ? "done" : "active"}`}>
            {wo.status.replace("_", " ")}
          </span>
        </span>
        <span className="wo-fault">
          {wo.fault_mode.replace("_", " ")}
          <br />
          {(wo.confidence * 100).toFixed(0)}% confidence
        </span>
      </div>

      <dl className="wo-grid">
        <dt>Asset</dt>
        <dd>{wo.asset_id}</dd>
        <dt>Component</dt>
        <dd>{wo.component ? wo.component.replace(/_/g, " ") : "—"}</dd>
        <dt>Part</dt>
        <dd>{wo.part || "—"}</dd>
        <dt>Technician</dt>
        <dd>
          {wo.technician_name || "unassigned"}
          {wo.technician_located_via === "live" || wo.technician_located_via === "mock" ? (
            <span className="via"> · network-located</span>
          ) : null}
        </dd>
        <dt>Position</dt>
        <dd>
          {wo.asset_latitude.toFixed(4)}, {wo.asset_longitude.toFixed(4)}
        </dd>
      </dl>

      {wo.nearest_skipped_name && (
        <div className="wo-why">
          {wo.nearest_skipped_name} is nearer at {wo.nearest_skipped_km.toFixed(1)} km but is not
          carrying a {wo.part}. A closer technician who cannot fix it is a second trip.
        </div>
      )}

      <div className="wo-eta">
        <span className="big">{wo.eta_minutes}</span>
        <span className="lbl">min out</span>
        <span style={{ flex: 1 }} />
        <span className="big" style={{ fontSize: 16 }}>
          {wo.distance_km.toFixed(1)}
        </span>
        <span className="lbl">km</span>
      </div>

      <div className="wo-actions">
        {!done && (
          <button className="btn tiny" disabled={busy} onClick={() => act(completeWorkOrder)}>
            Mark complete
          </button>
        )}
        <button className="btn tiny ghost" disabled={busy} onClick={() => act(deleteWorkOrder)}>
          Delete
        </button>
      </div>

      {err && <div className="hint err">{err}</div>}
    </div>
  );
}
