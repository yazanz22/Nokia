import type { AssetState, MaintenanceType } from "../types";

/** Minutes as a duration a dispatcher reads at a glance: "1h 58m", "34m". */
export function minutes(m: number): string {
  // Zero is a legitimate ETA: a technician already at the machine with nothing to
  // collect. Treating it as missing printed "Arrives: n/a" for the fastest
  // possible dispatch. The genuinely-unassigned case is handled by the caller,
  // which does not render an ETA at all.
  if (!Number.isFinite(m) || m < 0) return "n/a";
  if (m < 1) return "now";
  const h = Math.floor(m / 60);
  const rem = Math.round(m % 60);
  return h > 0 ? `${h}h ${String(rem).padStart(2, "0")}m` : `${rem}m`;
}

/** "1 machine", "3 machines". */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** Site names arrive prefixed ("NEOM - Trojena Ridge"). Show the working area. */
export function siteLabel(site: string): string {
  return site.replace(/^.*—\s*/, "");
}

/**
 * Hours against a service interval. Negative reads as overdue, not as a minus.
 *
 * The backend calls a machine overdue at `<= 0`, and both tables style on the same
 * boundary, so at exactly zero this used to print "in 0h" in overdue red. Either
 * side of it was worse: -0.4 rounded to "0h overdue" and +0.4 to "in 0h", two
 * opposite words for the same rounded quantity.
 */
export function serviceDue(h: number): string {
  if (!Number.isFinite(h)) return "n/a";
  const r = Math.round(h);
  if (r === 0) return "due now";
  return h <= 0 ? `${Math.abs(r)}h overdue` : `in ${r}h`;
}

export function km(v: number): string {
  return `${v.toFixed(1)} km`;
}

export function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

/** Seconds elapsed since an ISO timestamp. */
export function agoSeconds(iso: string): number {
  return Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
}

export function ago(iso: string): string {
  const s = agoSeconds(iso);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Words the operator uses, not the enum the backend stores. */
export const ASSET_STATE_LABEL: Record<AssetState, string> = {
  healthy: "Healthy",
  anomaly: "Needs attention",
  silent: "Needs attention",
  blindspot: "No coverage",
  dispatched: "Being handled",
};

/**
 * Map and legend colour groups.
 *
 * Five backend states collapse to four displayed groups. `silent` and `anomaly`
 * are one thing to the person looking at the map: something is wrong with this
 * machine and the agent is on it. Splitting them cost a legend entry and bought
 * a distinction only the backend cares about.
 */
export type StateGroup = "healthy" | "attention" | "nocoverage" | "handled";

export const STATE_GROUP: Record<AssetState, StateGroup> = {
  healthy: "healthy",
  anomaly: "attention",
  silent: "attention",
  blindspot: "nocoverage",
  dispatched: "handled",
};

export const GROUP_LABEL: Record<StateGroup, string> = {
  healthy: "Healthy",
  attention: "Needs attention",
  nocoverage: "No coverage",
  handled: "Being handled",
};

export const MAINTENANCE_LABEL: Record<MaintenanceType, string> = {
  corrective: "Corrective",
  preventive: "Preventive",
  predictive: "Predictive",
};

/** Why this job exists, in one line, for a card header. */
export const MAINTENANCE_WHY: Record<MaintenanceType, string> = {
  corrective: "The machine failed. Unplanned repair.",
  preventive: "Service interval came due. Nothing is wrong.",
  predictive: "Forecast expects a failure. Nothing has failed yet.",
};

export const WORK_ORDER_STATUS_LABEL: Record<string, string> = {
  queued: "Waiting for a technician",
  awaiting_part: "Waiting for a part",
  created: "Raised",
  assigned: "Assigned",
  completed: "Completed",
};

/**
 * Reorder points, mirrored from `backend/app/seed.py::PART_REORDER_AT`.
 *
 * Duplicated deliberately and narrowly: the nav badge has to count low lines
 * from the websocket without the Inventory tab being open, and the endpoint that
 * knows the real thresholds is only fetched by that tab. A flat "one or fewer"
 * rule counted a different set of lines from the tab's own header, so the two
 * badges for one concept disagreed on screen. If a threshold changes in the
 * backend it has to change here too; `test_no_duplicate_contracts.py` is where a
 * guard for that would go.
 */
export const REORDER_AT: Record<string, number> = {
  "HYD-PUMP-40L": 1,
  "RADIATOR-CORE-XL": 1,
  "BEARING-SET-90": 1,
  "ALTERNATOR-24V": 1,
  "SERVICE-KIT-500": 4,
};
