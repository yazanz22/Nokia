import type { Incident } from "../types";

const LABEL: Record<string, string> = {
  open: "open",
  investigating: "investigating",
  network_blindspot: "blind spot · no dispatch",
  hardware_confirmed: "hardware · dispatched",
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
  if (sorted.length === 0) return <div className="trace-empty">No incidents. Fleet nominal.</div>;
  return (
    <>
      {sorted.map((i) => (
        <div
          key={i.id}
          className="incident"
          onClick={() => onSelect(i.id)}
          style={{ cursor: "pointer", outline: i.id === selectedId ? "1px solid #37b6ff" : "none" }}
        >
          <div className="head">
            <span className="id">
              {i.id} · {i.asset_id}
            </span>
            <span className={`badge ${i.status}`}>{LABEL[i.status] ?? i.status}</span>
          </div>
          <div className="sum">{i.summary}</div>
          {i.resolution && <div className="res">{i.resolution}</div>}
        </div>
      ))}
    </>
  );
}
