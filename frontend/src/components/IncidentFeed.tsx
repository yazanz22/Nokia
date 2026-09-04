import type { Incident } from "../types";

const LABEL: Record<string, string> = {
  open: "open",
  investigating: "investigating",
  network_blindspot: "blind spot · no dispatch",
  no_fault: "no fault · no dispatch",
  roaming_blocked: "roaming · no dispatch",
  // Two dispatch outcomes, deliberately distinct: a sensor kit on a working machine is
  // not the same event as a mechanic and a heavy component.
  sensor_confirmed: "sensor · dispatched",
  hardware_confirmed: "hardware · dispatched",
  // Diagnosed and raised, but the whole crew is on jobs — the work order is queued
  // and nobody is en route. Says so plainly rather than borrowing "dispatched".
  awaiting_crew: "queued · nobody free",
  closed: "closed",
};

export function IncidentFeed({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: Incident[];
  selectedId: string | null;
  onSelect: (incidentId: string) => void;
}) {
  const sorted = [...incidents].sort((a, b) => b.opened_at.localeCompare(a.opened_at));

  if (sorted.length === 0)
    return (
      <div className="empty">
        <strong>All clear</strong>
        <span>Every asset is reporting. Nothing needs a decision right now.</span>
      </div>
    );

  return (
    <>
      {sorted.map((i) => (
        <div
          key={i.id}
          className={`incident ${i.status}${i.id === selectedId ? " sel" : ""}`}
          // A div that selects an incident is a button in everything but markup: without
          // these it cannot be reached or fired from the keyboard at all.
          role="button"
          tabIndex={0}
          aria-pressed={i.id === selectedId}
          onClick={() => onSelect(i.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onSelect(i.id);
            }
          }}
        >
          <div className="head">
            <span className="id">
              {i.id} · {i.asset_id}
            </span>
            <span className={`badge ${i.status}`}>{LABEL[i.status] ?? i.status}</span>
          </div>
          <p className="sum">{i.summary}</p>
          {i.resolution && <div className="res">{i.resolution}</div>}
        </div>
      ))}
    </>
  );
}
