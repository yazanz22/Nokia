import type { Asset, TelemetrySample } from "../types";

function Spark({
  label,
  unit,
  values,
  lo,
  hi,
}: {
  label: string;
  unit: string;
  values: number[];
  lo: number;
  hi: number;
}) {
  const w = 240;
  const h = 34;
  const last = values.at(-1);
  const span = hi - lo || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * w;
      const y = h - ((Math.min(Math.max(v, lo), hi) - lo) / span) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="spark">
      <div className="cap">
        <span>{label}</span>
        <span>{last !== undefined ? `${last.toFixed(1)} ${unit}` : "—"}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <polyline points={pts} fill="none" stroke="#37b6ff" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

export function AssetDrawer({
  asset,
  history,
  latest,
}: {
  asset: Asset | null;
  history: TelemetrySample[];
  latest: TelemetrySample | null;
}) {
  if (!asset) return <div className="trace-empty">Select an asset on the map.</div>;
  const h = history.length ? history : latest ? [latest] : [];
  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <strong>{asset.label}</strong> <span className="id">({asset.id})</span>
        <div className="res">
          {asset.site} · state: {asset.state}
        </div>
      </div>
      <Spark label="Engine temp" unit="°C" values={h.map((s) => s.engine_temp_c)} lo={60} hi={135} />
      <Spark
        label="Signal strength"
        unit="dBm"
        values={h.map((s) => s.signal_strength_dbm)}
        lo={-135}
        hi={-40}
      />
      <Spark
        label="Telemetry age"
        unit="s"
        values={h.map((s) => s.telemetry_age_sec)}
        lo={0}
        hi={120}
      />
      <Spark
        label="Neighbour-cell failures"
        unit=""
        values={h.map((s) => s.neighbor_fail_count)}
        lo={0}
        hi={15}
      />
    </div>
  );
}
