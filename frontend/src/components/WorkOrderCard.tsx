import { useState } from "react";
import { completeWorkOrder, deleteWorkOrder } from "../lib/api";
import type { WorkOrder } from "../types";

// The component model routinely answers 0.9999999979, and a plain round prints
// "100% confidence" — a claim no model can defend and the first thing anyone will
// challenge. Above 99.5% we say ">99%" instead: honest about the magnitude without
// asserting certainty. A decimal place would have printed "100.0%", which is worse.
const pct = (v: number) => (v >= 0.995 ? ">99%" : `${(v * 100).toFixed(0)}%`);

export function WorkOrderCard({ wo }: { wo: WorkOrder }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const done = wo.status === "completed";
  // Raised, part named, nobody assigned: the whole crew is already on jobs. Nothing
  // about this card may read as a truck in motion.
  const queued = wo.status === "queued";

  // Two separate models produce two separate numbers, and unlabelled they get read
  // as one: `confidence` is the classifier's confidence in the *fault mode*, while
  // this is the prognostic model's confidence in the *component* it named. The
  // shared WorkOrder type is owned elsewhere, so read the field locally.
  const componentConfidence =
    wo.component_confidence ?? 0;

  // The list is driven by the websocket, so there is nothing to update locally —
  // this only guards against a double-click while the request is in flight.
  //
  // Release it in `finally`, not just on failure. Deleting unmounts the card so it
  // never mattered there, but completing leaves the card on screen: the flag stayed
  // set, and the Delete button next to it — disabled={busy} — was dead from then on.
  const act = async (fn: (id: string) => Promise<unknown>) => {
    setBusy(true);
    setErr("");
    try {
      await fn(wo.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`wo${done ? " wo-done" : ""}`}>
      <div className="wo-top">
        <span className="wo-id">
          {wo.id}
          <span className={`wo-status ${done ? "done" : queued ? "queued" : "active"}`}>
            {wo.status.replace("_", " ")}
          </span>
        </span>
        <span className="wo-fault">
          {wo.fault_mode.replace("_", " ")}
          <br />
          <span className="conf">{pct(wo.confidence)} fault-mode confidence</span>
        </span>
      </div>

      <dl className="wo-grid">
        <dt>Asset</dt>
        <dd>{wo.asset_id}</dd>
        <dt>Component</dt>
        <dd>
          {wo.component ? wo.component.replace(/_/g, " ") : "—"}
          {wo.component && componentConfidence > 0 ? (
            <span className="conf"> · {pct(componentConfidence)} component confidence</span>
          ) : null}
        </dd>
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

      {queued ? (
        // Nobody is assigned, so there is no route and no ETA — the fields are zero.
        // Printed as the usual block that reads "0 min out / 0.0 km", which looks like
        // a technician already standing at the machine rather than one nobody has sent.
        <div className="wo-wait">
          <span className="wo-wait-lbl">waiting for a free technician</span>
          <span className="wo-wait-sub">
            The fault is confirmed and the part is named. The job is handed to the first
            technician who finishes — nobody is en route yet.
          </span>
        </div>
      ) : (
        <div className="wo-eta">
          <span className="big">{wo.eta_minutes}</span>
          <span className="lbl">min out</span>
          <span style={{ flex: 1 }} />
          <span className="big" style={{ fontSize: 16 }}>
            {wo.distance_km.toFixed(1)}
          </span>
          <span className="lbl">km</span>
        </div>
      )}

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
