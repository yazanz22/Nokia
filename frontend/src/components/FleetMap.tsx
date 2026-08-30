import { useMemo } from "react";
import type { Asset, Technician, WorkOrder } from "../types";

const W = 620;
const H = 460;
const PAD = 34;

const STATE_COLOR: Record<string, string> = {
  healthy: "#35d07f",
  anomaly: "#ffb020",
  silent: "#ff5c6c",
  blindspot: "#a98bff",
  dispatched: "#37b6ff",
};

interface Props {
  assets: Asset[];
  technicians: Technician[];
  workOrders: WorkOrder[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function FleetMap({ assets, technicians, workOrders, selectedId, onSelect }: Props) {
  const project = useMemo(() => {
    const lats = [...assets, ...technicians].map((p) => p.latitude);
    const lons = [...assets, ...technicians].map((p) => p.longitude);
    const latLo = Math.min(...lats), latHi = Math.max(...lats);
    const lonLo = Math.min(...lons), lonHi = Math.max(...lons);
    const spanLat = latHi - latLo || 1;
    const spanLon = lonHi - lonLo || 1;
    return (lat: number, lon: number): [number, number] => {
      const x = PAD + ((lon - lonLo) / spanLon) * (W - 2 * PAD);
      const y = PAD + ((latHi - lat) / spanLat) * (H - 2 * PAD); // north up
      return [x, y];
    };
  }, [assets, technicians]);

  const activeWOs = workOrders.filter((w) => w.technician_id);

  return (
    <div className="map-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M40 0H0V40" fill="none" stroke="#1c2740" strokeWidth="1" />
          </pattern>
        </defs>
        <rect x="0" y="0" width={W} height={H} fill="#0d131f" />
        <rect x={PAD} y={PAD} width={W - 2 * PAD} height={H - 2 * PAD} fill="url(#grid)" stroke="#263247" />
        <text x={PAD} y={PAD - 12} fill="#8a99ad" fontSize="11">
          NEOM / Gulf of Aqaba — network-verified asset positions
        </text>

        {/* dispatch routes */}
        {activeWOs.map((w) => {
          const tech = technicians.find((t) => t.id === w.technician_id);
          if (!tech) return null;
          const [ax, ay] = project(w.asset_latitude, w.asset_longitude);
          const [tx, ty] = project(tech.latitude, tech.longitude);
          return (
            <g key={`route-${w.id}`}>
              <line x1={tx} y1={ty} x2={ax} y2={ay} stroke="#37b6ff" strokeWidth="1.5" strokeDasharray="5 4">
                <animate attributeName="stroke-dashoffset" from="9" to="0" dur="0.7s" repeatCount="indefinite" />
              </line>
              <text x={(ax + tx) / 2} y={(ay + ty) / 2 - 4} fill="#37b6ff" fontSize="10" textAnchor="middle">
                {w.id} · {w.eta_minutes}m
              </text>
            </g>
          );
        })}

        {/* technicians */}
        {technicians.map((t) => {
          const [x, y] = project(t.latitude, t.longitude);
          return (
            <g key={t.id}>
              <rect x={x - 4} y={y - 4} width="8" height="8" fill={t.available ? "#5b6b82" : "#37b6ff"} />
              <text x={x + 8} y={y + 3} fill="#8a99ad" fontSize="9">
                {t.name.split(" ")[0]}
              </text>
            </g>
          );
        })}

        {/* assets */}
        {assets.map((a) => {
          const [x, y] = project(a.latitude, a.longitude);
          const c = STATE_COLOR[a.state] ?? "#8a99ad";
          const sel = a.id === selectedId;
          const pulse = a.state === "silent" || a.state === "anomaly";
          return (
            <g key={a.id} onClick={() => onSelect(a.id)} style={{ cursor: "pointer" }}>
              {pulse && (
                <circle cx={x} cy={y} r="10" fill="none" stroke={c} strokeWidth="1.5" opacity="0.6">
                  <animate attributeName="r" from="6" to="16" dur="1.4s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.6" to="0" dur="1.4s" repeatCount="indefinite" />
                </circle>
              )}
              <circle cx={x} cy={y} r={sel ? 7 : 5} fill={c} stroke={sel ? "#e6edf6" : "#0d131f"} strokeWidth={sel ? 2 : 1} />
              {sel && (
                <text x={x + 9} y={y + 3} fill="#e6edf6" fontSize="10">
                  {a.id}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="legend">
        {Object.entries(STATE_COLOR).map(([k, v]) => (
          <span key={k}>
            <i style={{ background: v }} />
            {k}
          </span>
        ))}
      </div>
    </div>
  );
}
