import { useEffect, useRef, useState } from "react";
import type { Kpis } from "../types";

// A dispatch that never happened is the product, but "2" is not a number anyone
// repeats afterwards — the money is. Range rather than a point estimate, because
// the source gives a range: $250–$600 per truck roll, "in some cases as high as
// $1,000" (see docs/EVIDENCE.md). Shown as an illustrative rate, not a measurement.
const TRUCK_ROLL_LOW = 250;
const TRUCK_ROLL_HIGH = 1000;

function money(n: number): string {
  return n >= 1000 ? `$${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}k` : `$${n}`;
}

/** Counts up to a new value so a change reads as an event, not a redraw. */
function useCountUp(target: number, ms = 550): number {
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (target === from.current) return;
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / ms, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setV(a + (target - a) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

export function KpiBar({ kpis }: { kpis: Kpis | null }) {
  const k = kpis ?? {
    fleet_size: 0,
    available_assets: 0,
    fleet_availability_pct: 100,
    open_incidents: 0,
    false_dispatches_avoided: 0,
    incidents_prevented: 0,
    dispatches_issued: 0,
    avg_triage_seconds: 0,
  };

  // These two carry the entire argument, so they get the visual weight.
  const avoided = useCountUp(k.false_dispatches_avoided);
  const issued = useCountUp(k.dispatches_issued);

  return (
    <div className="kpis">
      <Kpi
        hero
        rail="var(--ok)"
        value={Math.round(avoided).toString()}
        label="False dispatches avoided"
        tone={k.false_dispatches_avoided > 0 ? "ok" : "idle"}
        note={
          k.false_dispatches_avoided > 0
            ? `${money(k.false_dispatches_avoided * TRUCK_ROLL_LOW)}–${money(
                k.false_dispatches_avoided * TRUCK_ROLL_HIGH
              )} saved`
            : undefined
        }
        noteTitle="Illustrative: $250–$1,000 per truck roll (docs/EVIDENCE.md). Not a measured saving."
      />
      <Kpi
        hero
        rail="var(--hv)"
        value={Math.round(issued).toString()}
        label="Dispatches issued"
        tone={k.dispatches_issued > 0 ? "hv" : "idle"}
      />
      <Kpi
        value={`${k.incidents_prevented ?? 0}`}
        label="Incidents prevented"
        tone={(k.incidents_prevented ?? 0) > 0 ? "ok" : "idle"}
      />
      <Kpi value={`${k.fleet_availability_pct.toFixed(1)}%`} label="Fleet availability" />
      <Kpi value={`${k.available_assets}/${k.fleet_size}`} label="Assets online" />
      <Kpi
        value={`${k.open_incidents}`}
        label="Open incidents"
        tone={k.open_incidents ? "warn" : "idle"}
      />
      <Kpi
        value={k.avg_triage_seconds ? `${k.avg_triage_seconds.toFixed(0)}s` : "—"}
        label="Avg triage time"
      />
    </div>
  );
}

function Kpi({
  value,
  label,
  tone,
  hero,
  rail,
  note,
  noteTitle,
}: {
  value: string;
  label: string;
  tone?: "ok" | "hv" | "warn" | "idle";
  hero?: boolean;
  rail?: string;
  note?: string;
  noteTitle?: string;
}) {
  return (
    <div
      className={`kpi${hero ? " hero" : ""}`}
      style={rail ? ({ "--rail": rail } as React.CSSProperties) : undefined}
    >
      <div className={`v ${tone ?? ""}`}>{value}</div>
      <div className="l">{label}</div>
      {note && (
        <div className="kpi-note" title={noteTitle}>
          {note}
        </div>
      )}
    </div>
  );
}
