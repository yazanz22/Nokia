import type { Incident } from "../types";

const LABEL: Record<string, string> = {
  open: "open",
  investigating: "investigating",
  network_blindspot: "blind spot · no dispatch",
  no_fault: "no fault · no dispatch",
  roaming_blocked: "roaming · no dispatch",
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
          onClick={() => onSelect(i.id)}
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
