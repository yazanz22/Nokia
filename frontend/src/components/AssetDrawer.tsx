import type { Asset, RiskRow, TelemetrySample } from "../types";

function Spark({
  label,
  unit,
  values,
  lo,
  hi,
  color = "#5aa9e6",
}: {
  label: string;
  unit: string;
  values: number[];
  lo: number;
  hi: number;
  color?: string;
}) {
  const w = 260;
  const h = 28;
  const last = values.at(-1);
  const span = hi - lo || 1;
  const at = (v: number, i: number): [number, number] => [
    (i / Math.max(values.length - 1, 1)) * w,
    h - ((Math.min(Math.max(v, lo), hi) - lo) / span) * h,
  ];
  const pts = values.map(at);
  const line = pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = pts.length
    ? `M0,${h} L${line.split(" ").join(" L")} L${w},${h} Z`
    : "";

  return (
    <div className="spark">
      <div className="cap">
        <span>{label}</span>
        <b>{last !== undefined ? `${last.toFixed(1)}${unit}` : "—"}</b>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        {area && <path d={area} fill={color} opacity="0.13" />}
        {pts.length > 0 && (
          <polyline points={line} fill="none" stroke={color} strokeWidth="1.6" />
        )}
        {pts.length > 0 && (
          <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.4" fill={color} />
        )}
      </svg>
    </div>
  );
}

export function AssetDrawer({
  asset,
  history,
  latest,
  risk = null,
}: {
  asset: Asset | null;
  history: TelemetrySample[];
  latest: TelemetrySample | null;
  risk?: RiskRow | null;
}) {
  if (!asset)
    return (
      <div className="empty">
        <strong>No asset selected</strong>
        <span>Pick a machine on the map to see its live channels.</span>
      </div>
    );

  const h = history.length ? history : latest ? [latest] : [];

  // "healthy" is a statement about right now — the machine is streaming and every
  // channel is nominal. The forecast is a different claim entirely, and a status
  // chip that only ever says healthy hides it. Both are true at once, so show both.
  const forecast = risk && risk.at_risk ? risk : null;

  return (
    <div>
      <div className="tele-head">
        <div>
          <div className="tele-name">{asset.label}</div>
          <div className="tele-site">
            {asset.id} · {asset.site}
          </div>
        </div>
        <div className="tele-badges">
          <span className={`badge ${asset.state === "healthy" ? "" : "investigating"}`}>
            {asset.state}
          </span>
          {forecast && (
            <span className="badge forecast" title="From the prognostic model, not the live channels.">
              at risk
              {forecast.horizon_hours ? ` · ~${forecast.horizon_hours}h` : ""}
            </span>
          )}
        </div>
      </div>

      {forecast && (
        <div className="tele-forecast">
          <strong>Streaming normally, and predicted to fail.</strong> Vibration{" "}
          {forecast.vibration_mm_s.toFixed(2)} mm/s
          {forecast.vibration_delta > 0 ? ` (+${forecast.vibration_delta.toFixed(2)})` : ""}, oil
          particles {Math.round(forecast.oil_particle_count)}
          {forecast.oil_particle_delta > 0
            ? ` (+${Math.round(forecast.oil_particle_delta)})`
            : ""}
          . Both lead engine temperature by days, which is why the live channels above still
          look fine.
        </div>
      )}

      <div className="sparks">
        <Spark label="Engine temp" unit="°C" values={h.map((s) => s.engine_temp_c)} lo={60} hi={135}
               color="#ffb648" />
        <Spark label="Signal" unit=" dBm" values={h.map((s) => s.signal_strength_dbm)} lo={-135}
               hi={-40} color="#46d39a" />
        <Spark label="Telemetry age" unit="s" values={h.map((s) => s.telemetry_age_sec)} lo={0}
               hi={120} color="#5aa9e6" />
        <Spark label="Neighbour failures" unit="" values={h.map((s) => s.neighbor_fail_count)} lo={0}
               hi={15} color="#ff5f52" />
      </div>
    </div>
  );
}
