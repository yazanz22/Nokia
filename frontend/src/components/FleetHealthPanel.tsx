import { useEffect, useState } from "react";
import { getFleetHealth } from "../lib/api";

interface RiskRow {
  asset_id: string;
  label?: string;
  site?: string;
  risk: number;
  horizon_hours: number | null;
  at_risk: boolean;
  vibration_mm_s: number;
  vibration_delta: number;
  oil_particle_count: number;
  oil_particle_delta: number;
}

/**
 * The proactive half of the system: machines that have NOT failed yet, ranked by how
 * soon the model expects them to. Each row shows the two channels that actually
 * moved — vibration and oil particles — because those trend days before engine
 * temperature does, and that gap is why this is a model and not a threshold.
 */
export function FleetHealthPanel({ onSelect }: { onSelect: (id: string) => void }) {
  const [rows, setRows] = useState<RiskRow[]>([]);
  const [available, setAvailable] = useState(true);
  const [atRisk, setAtRisk] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getFleetHealth()
      .then((d) => {
        if (cancelled) return;
        setAvailable(d.available);
        setAtRisk(d.at_risk ?? 0);
        setRows(d.assets ?? []);
      })
      .catch(() => setAvailable(false));
    return () => {
      cancelled = true;
    };
  }, []);

  if (!available)
    return (
      <div className="empty">
        <strong>Forecasting offline</strong>
        <span>
          Run <code>python ml/train.py</code> to build the model.
        </span>
      </div>
    );

  const risky = rows.filter((r) => r.at_risk);

  return (
    <div>
      <div className="health-head">
        <span className="health-count">{atRisk}</span>
        <span className="health-lbl">
          of {rows.length} machines
          <br />
          trending toward failure
        </span>
      </div>

      {risky.length === 0 && (
        <div className="empty">
          <strong>Fleet healthy</strong>
          <span>No machine is showing a degradation trend.</span>
        </div>
      )}

      {risky.map((r) => (
        <div className="risk-row" key={r.asset_id} onClick={() => onSelect(r.asset_id)}>
          <div className="risk-top">
            <span className="risk-id">{r.label ?? r.asset_id}</span>
            <span className={`horizon ${horizonClass(r.horizon_hours)}`}>
              {fmtHorizon(r.horizon_hours)}
            </span>
          </div>
          <div className="risk-sub">{r.asset_id}</div>
          <div className="risk-signals">
            <Signal name="vibration" value={`${r.vibration_mm_s}`} delta={r.vibration_delta} />
            <Signal name="oil particles" value={`${r.oil_particle_count}`} delta={r.oil_particle_delta} />
          </div>
        </div>
      ))}

      {risky.length > 0 && (
        <div className="hint">
          Ranked by the tightest horizon the model clears at 24 / 48 / 72 h. Vibration and
          oil-particle trends move days before engine temperature does.
        </div>
      )}
    </div>
  );
}

function Signal({ name, value, delta }: { name: string; value: string; delta: number }) {
  const up = delta > 0;
  return (
    <div className="sig">
      <span className="sig-name">{name}</span>
      <span className="sig-val">{value}</span>
      <span className={`sig-delta ${up ? "up" : ""}`}>
        {up ? "▲" : "▼"}
        {Math.abs(delta)}
      </span>
    </div>
  );
}

function fmtHorizon(h: number | null): string {
  if (h === null) return "—";
  if (h <= 24) return "< 1 day";
  return `~${Math.round(h / 24)} days`;
}

function horizonClass(h: number | null): string {
  if (h === null) return "";
  if (h <= 24) return "urgent";
  if (h <= 48) return "soon";
  return "watch";
}
