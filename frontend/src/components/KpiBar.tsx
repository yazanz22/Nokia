import type { Kpis } from "../types";

const fmt = (n: number, d = 0) => n.toFixed(d);

export function KpiBar({ kpis }: { kpis: Kpis | null }) {
  const k = kpis ?? {
    fleet_size: 0,
    available_assets: 0,
    fleet_availability_pct: 100,
    open_incidents: 0,
    false_dispatches_avoided: 0,
    dispatches_issued: 0,
    avg_triage_seconds: 0,
  };
  return (
    <div className="kpis">
      <Kpi label="Fleet availability" value={`${fmt(k.fleet_availability_pct, 1)}%`} tone={k.fleet_availability_pct >= 90 ? "good" : "warn"} />
      <Kpi label="Assets online" value={`${k.available_assets}/${k.fleet_size}`} />
      <Kpi label="Open incidents" value={`${k.open_incidents}`} tone={k.open_incidents ? "warn" : undefined} />
      <Kpi label="False dispatches avoided" value={`${k.false_dispatches_avoided}`} tone="good" />
      <Kpi label="Dispatches issued" value={`${k.dispatches_issued}`} />
      <Kpi label="Avg triage time" value={`${fmt(k.avg_triage_seconds, 0)}s`} />
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" }) {
  return (
    <div className="kpi">
      <div className={`v ${tone ?? ""}`}>{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}
