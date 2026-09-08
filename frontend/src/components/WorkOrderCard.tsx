import { Package, Path, Timer, Warning } from "@phosphor-icons/react";
import type { WorkOrder } from "../types";
import {
  MAINTENANCE_LABEL,
  MAINTENANCE_WHY,
  WORK_ORDER_STATUS_LABEL,
  km,
  minutes,
  pct,
  plural,
} from "../lib/format";

const STATUS_TONE: Record<string, string> = {
  assigned: "is-accent",
  created: "is-accent",
  queued: "is-warn",
  awaiting_part: "is-warn",
  completed: "is-ok",
};

const TYPE_TONE: Record<string, string> = {
  corrective: "is-bad",
  preventive: "is-ok",
  predictive: "is-warn",
};

/**
 * One job.
 *
 * The card leads with what broke and who is going, then explains the journey,
 * because since components moved into depots the journey is the part that needs
 * explaining: the assigned technician is regularly not the nearest one, and on a
 * map that looks like a bug until the card says why.
 */
export function WorkOrderCard({
  wo,
  onComplete,
  onNoFault,
  onDelete,
  busy,
}: {
  wo: WorkOrder;
  onComplete?: (id: string) => void;
  onNoFault?: (id: string) => void;
  onDelete?: (id: string) => void;
  busy?: boolean;
}) {
  const unassigned = !wo.technician_id;

  return (
    <article className="wo">
      <header className="wo-head">
        <span className="mono text-xs">{wo.id}</span>
        <span className={`badge ${TYPE_TONE[wo.maintenance_type] ?? ""}`}>
          {MAINTENANCE_LABEL[wo.maintenance_type]}
        </span>
        <span className={`badge ${STATUS_TONE[wo.status] ?? ""}`}>
          {wo.no_fault_found
            ? "No fault found"
            : (WORK_ORDER_STATUS_LABEL[wo.status] ?? wo.status)}
        </span>
      </header>

      <p className="wo-why text-xs text-muted">{MAINTENANCE_WHY[wo.maintenance_type]}</p>

      <dl className="dl">
        <dt>Machine</dt>
        <dd className="mono">{wo.asset_id}</dd>

        {wo.component && (
          <>
            <dt>Component</dt>
            <dd>
              {wo.component.replace(/_/g, " ")}
              {wo.component_confidence > 0 && (
                <span className="text-muted text-xs"> at {pct(wo.component_confidence)}</span>
              )}
            </dd>
          </>
        )}

        <dt>Part</dt>
        <dd className="mono">
          {wo.part || "n/a"}
          {wo.bundled_service && <span className="badge is-ok">Plus service</span>}
        </dd>

        {!unassigned && (
          <>
            <dt>Technician</dt>
            <dd>
              {wo.technician_name}
              {wo.technician_located_via !== "seed" && (
                <span className="text-muted text-xs"> located by the network</span>
              )}
            </dd>

            <dt>Arrives</dt>
            <dd className="mono">{minutes(wo.eta_minutes)}</dd>
          </>
        )}
      </dl>

      {/* The route. Two legs and a loading stop when the part comes off a shelf,
          one leg when it was already in the van. */}
      {!unassigned && (
        <div className="wo-route">
          {wo.warehouse_id ? (
            <>
              <span className="wo-leg">
                <Path size={13} aria-hidden />
                {km(wo.leg_to_warehouse_km)} to {wo.warehouse_name}
              </span>
              <span className="wo-leg">
                <Package size={13} aria-hidden />
                {wo.loading_minutes}m loading
              </span>
              <span className="wo-leg">
                <Timer size={13} aria-hidden />
                {km(wo.leg_to_asset_km)} to the machine
              </span>
            </>
          ) : (
            <span className="wo-leg">
              <Path size={13} aria-hidden />
              {km(wo.distance_km)} direct, part carried in the van
            </span>
          )}
        </div>
      )}

      {/* Why a closer technician was passed over. Without this the dispatch reads
          as a routing error to anybody looking at the map. */}
      {/* Only when there is a real penalty to report. A rounded zero produced
          "would arrive 0 minutes later" inside a sentence explaining why they are
          slower, which is worse than saying nothing. */}
      {wo.nearest_skipped_name && wo.nearest_skipped_minutes_later > 0 && (
        <p className="wo-note">
          <Warning size={14} aria-hidden />
          <span>
            <b>{wo.nearest_skipped_name}</b> is nearer the machine at{" "}
            {km(wo.nearest_skipped_km)}, but would arrive{" "}
            <b>{plural(wo.nearest_skipped_minutes_later, "minute")} later</b> once the
            part is collected. Closer is not sooner when the part is not in the van.
          </span>
        </p>
      )}

      {wo.status === "awaiting_part" && (
        <p className="wo-note is-bad">
          <Warning size={14} aria-hidden />
          <span>
            No depot on site stocks a <b>{wo.part}</b>. Nobody has been sent, because
            there is nothing for them to collect. Receipt stock on the Inventory tab to
            release this job.
          </span>
        </p>
      )}

      {wo.status === "queued" && (
        <p className="wo-note">
          <Warning size={14} aria-hidden />
          <span>
            Every technician is already on a job. This one is next when somebody frees.
          </span>
        </p>
      )}

      {wo.no_fault_found && (
        <p className="wo-note">
          <Warning size={14} aria-hidden />
          <span>
            The technician attended and found nothing to repair. The {wo.part} went back
            to {wo.warehouse_name || "the depot"} unfitted, and the journey is counted
            against this system rather than filed as a repair.
          </span>
        </p>
      )}

      {(onComplete || onNoFault || onDelete) && wo.status !== "completed" && (
        <footer className="wo-actions">
          {onComplete && !unassigned && (
            <button className="btn btn-sm" disabled={busy} onClick={() => onComplete(wo.id)}>
              Mark complete
            </button>
          )}
          {/* Only offered once somebody is actually going. A job with no technician
              on it was never attended, so "no fault found" would be a lie about it;
              that one gets cancelled instead. */}
          {onNoFault && !unassigned && (
            <button
              className="btn btn-sm"
              disabled={busy}
              onClick={() => onNoFault(wo.id)}
              title="The technician attended and found nothing to repair. Returns the part to its depot."
            >
              No fault found
            </button>
          )}
          {onDelete && (
            <button
              className="btn btn-sm btn-ghost btn-danger"
              disabled={busy}
              onClick={() => onDelete(wo.id)}
            >
              Cancel
            </button>
          )}
        </footer>
      )}
    </article>
  );
}
