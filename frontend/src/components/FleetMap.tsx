import { useMemo } from "react";
import type { Asset, DeadZone, Technician, WorkOrder } from "../types";

// Mirrors nac/base.py — the operational site perimeter.
const SITE_CENTER: [number, number] = [27.5581, 34.9196];
const SITE_RADIUS_KM = 80;

const W = 900;
const H = 640;
const PAD = 46;

const STATE_COLOR: Record<string, string> = {
  healthy: "#46d39a",
  anomaly: "#ffb648",
  silent: "#ff5f52",
  blindspot: "#5aa9e6",
  dispatched: "#ffc266",
};

const STATE_LABEL: Record<string, string> = {
  healthy: "healthy",
  anomaly: "anomaly",
  silent: "silent",
  blindspot: "blind spot",
  dispatched: "dispatched",
};

interface Props {
  assets: Asset[];
  technicians: Technician[];
  riskById?: Record<string, { horizon_hours: number | null }>;
  workOrders: WorkOrder[];
  deadZones: DeadZone[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** Convex hull (monotone chain) — used to outline each site's working area. */
function hull(pts: [number, number][]): [number, number][] {
  if (pts.length < 3) return pts;
  const p = [...pts].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: number[], a: number[], b: number[]) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const build = (src: [number, number][]) => {
    const out: [number, number][] = [];
    for (const q of src) {
      while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], q) <= 0) out.pop();
      out.push(q);
    }
    out.pop();
    return out;
  };
  return [...build(p), ...build([...p].reverse())];
}

/** Expand a polygon outward from its centroid so the outline clears the markers. */
function inflate(poly: [number, number][], by: number): [number, number][] {
  if (poly.length === 0) return poly;
  const cx = poly.reduce((s, p) => s + p[0], 0) / poly.length;
  const cy = poly.reduce((s, p) => s + p[1], 0) / poly.length;
  return poly.map(([x, y]) => {
    const dx = x - cx;
    const dy = y - cy;
    const d = Math.hypot(dx, dy) || 1;
    return [x + (dx / d) * by, y + (dy / d) * by] as [number, number];
  });
}

export function FleetMap({ assets, technicians, workOrders, deadZones, riskById = {}, selectedId, onSelect }: Props) {
  // Equirectangular with a single scale for both axes. Stretching each axis
  // independently to fill the box makes the map lie about distance — at this latitude
  // it rendered east-west spans 1.85x larger than north-south ones, so a technician
  // who looked closer often was not. "Nearest" has to mean the same thing on the map
  // as it does in the dispatch.
  const project = useMemo(() => {
    const pts = [...assets, ...technicians];
    if (pts.length === 0) return () => [W / 2, H / 2] as [number, number];
    const lats = pts.map((p) => p.latitude);
    const lons = pts.map((p) => p.longitude);
    const latLo = Math.min(...lats);
    const latHi = Math.max(...lats);
    const lonLo = Math.min(...lons);
    const lonHi = Math.max(...lons);

    // Longitude degrees shrink with latitude; convert both spans to kilometres first.
    const midLat = (latLo + latHi) / 2;
    const kmPerLat = 111.32;
    const kmPerLon = 111.32 * Math.cos((midLat * Math.PI) / 180);
    const spanKmLat = Math.max((latHi - latLo) * kmPerLat, 0.001);
    const spanKmLon = Math.max((lonHi - lonLo) * kmPerLon, 0.001);

    // One scale, so a kilometre is the same number of pixels in every direction.
    const scale = Math.min((W - 2 * PAD) / spanKmLon, (H - 2 * PAD) / spanKmLat);
    const offX = (W - spanKmLon * scale) / 2;
    const offY = (H - spanKmLat * scale) / 2;

    return (lat: number, lon: number): [number, number] => [
      offX + (lon - lonLo) * kmPerLon * scale,
      offY + (latHi - lat) * kmPerLat * scale, // north up
    ];
  }, [assets, technicians]);

  // Site zones are genuine: every asset carries the site it works on.
  const zones = useMemo(() => {
    const bySite = new Map<string, [number, number][]>();
    for (const a of assets) {
      const p = project(a.latitude, a.longitude);
      const arr = bySite.get(a.site) ?? [];
      arr.push(p);
      bySite.set(a.site, arr);
    }
    return [...bySite.entries()]
      .filter(([, pts]) => pts.length >= 3)
      .map(([site, pts]) => {
        const poly = inflate(hull(pts), 22);
        const cx = poly.reduce((s, p) => s + p[0], 0) / poly.length;
        const cy = poly.reduce((s, p) => s + p[1], 0) / poly.length;
        return { site, d: poly.map((p) => p.join(",")).join(" "), cx, cy };
      });
  }, [assets, project]);

  // A real scale bar, now that a kilometre is the same length everywhere on the map.
  const scaleBar = useMemo(() => {
    const [x0] = project(27.0, 34.0);
    const [x1] = project(27.0, 34.0 + 1 / (111.32 * Math.cos((27.5 * Math.PI) / 180)));
    const pxPerKm = Math.abs(x1 - x0) || 1;
    const target = (W - 2 * PAD) / 4;
    const nice = [1, 2, 5, 10, 20, 25, 50, 100];
    const km = nice.reduce((best, k) =>
      Math.abs(k * pxPerKm - target) < Math.abs(best * pxPerKm - target) ? k : best, nice[0]);
    return { km, px: km * pxPerKm };
  }, [project]);

  // A finished job is not a journey. Without the status check the route kept
  // animating after the repair closed — and because completing a job frees the
  // technician back into the drifting pool, the line followed them around the site
  // still pointing at a machine that was already fixed.
  const activeWOs = workOrders.filter((w) => w.technician_id && w.status !== "completed");

  return (
    <div className="map-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" role="img"
           aria-label="Fleet map of the project site">
        <defs>
          <radialGradient id="terrain" cx="42%" cy="34%" r="78%">
            <stop offset="0%" stopColor="#16202f" />
            <stop offset="55%" stopColor="#111a27" />
            <stop offset="100%" stopColor="#0a1018" />
          </radialGradient>
          <pattern id="grid" width="45" height="45" patternUnits="userSpaceOnUse">
            <path d="M45 0H0V45" fill="none" stroke="#1b2536" strokeWidth="1" />
          </pattern>
          <filter id="soft" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="9" />
          </filter>
          <pattern id="deadzone" width="7" height="7" patternUnits="userSpaceOnUse"
                   patternTransform="rotate(45)">
            <rect width="7" height="7" fill="#5aa9e6" opacity="0.07" />
            <line x1="0" y1="0" x2="0" y2="7" stroke="#5aa9e6" strokeWidth="1.4" opacity="0.3" />
          </pattern>
        </defs>

        <rect width={W} height={H} fill="url(#terrain)" />
        <rect width={W} height={H} fill="url(#grid)" opacity="0.55" />

        {/* Contour suggestion — desert relief, purely atmospheric. */}
        <g stroke="#1e2a3c" fill="none" opacity="0.6">
          <path d="M-20 190 Q 190 130 380 200 T 780 175 T 960 215" strokeWidth="1" />
          <path d="M-20 250 Q 200 195 400 258 T 800 232 T 960 268" strokeWidth="1" />
          <path d="M-20 430 Q 230 372 450 438 T 850 408 T 960 442" strokeWidth="1" />
          <path d="M-20 496 Q 240 440 460 502 T 860 472 T 960 506" strokeWidth="1" />
        </g>

        {/* Coverage the agent has learned is bad. Nobody surveyed for this — it is
            the by-product of investigating incidents, drawn where they clustered. */}
        {deadZones.map((z) => {
          const [x1, y1] = project(z.latitude + z.span / 2, z.longitude - z.span / 2);
          const [x2, y2] = project(z.latitude - z.span / 2, z.longitude + z.span / 2);
          const w = Math.max(Math.abs(x2 - x1), 26);
          const h = Math.max(Math.abs(y2 - y1), 26);
          return (
            <g key={`dz-${z.latitude}-${z.longitude}`}>
              <rect x={Math.min(x1, x2)} y={Math.min(y1, y2)} width={w} height={h}
                    fill="url(#deadzone)" stroke="#5aa9e6" strokeWidth="1"
                    strokeDasharray="4 3" opacity="0.85" rx="3" />
              <text x={Math.min(x1, x2) + w / 2} y={Math.min(y1, y2) - 5} textAnchor="middle"
                    fill="#5aa9e6" fontSize="9.5" fontFamily="Barlow Condensed, sans-serif"
                    letterSpacing="1.1">
                DEAD ZONE · {z.incidents}
              </text>
            </g>
          );
        })}

        {/* Site working areas */}
        {zones.map((z) => (
          <g key={z.site}>
            <polygon points={z.d} fill="#1d2a3d" opacity="0.42" filter="url(#soft)" />
            <polygon
              points={z.d}
              fill="none"
              stroke="#2e3d54"
              strokeWidth="1"
              strokeDasharray="3 4"
            />
            <text
              x={z.cx}
              y={z.cy}
              textAnchor="middle"
              fill="#5d6980"
              fontSize="10.5"
              fontFamily="Barlow Condensed, sans-serif"
              letterSpacing="1.4"
              style={{ textTransform: "uppercase" }}
            >
              {z.site.replace(/^.*—\s*/, "")}
            </text>
          </g>
        ))}

        {/* Dispatch routes */}
        {activeWOs.map((w) => {
          const tech = technicians.find((t) => t.id === w.technician_id);
          if (!tech) return null;
          const [ax, ay] = project(w.asset_latitude, w.asset_longitude);
          const [tx, ty] = project(tech.latitude, tech.longitude);
          const mx = (ax + tx) / 2;
          const my = (ay + ty) / 2 - Math.hypot(ax - tx, ay - ty) * 0.16;
          const d = `M${tx},${ty} Q${mx},${my} ${ax},${ay}`;
          return (
            <g key={`route-${w.id}`}>
              <path d={d} fill="none" stroke="#ffc266" strokeWidth="1.6" opacity="0.5"
                    strokeDasharray="6 5">
                <animate attributeName="stroke-dashoffset" from="11" to="0" dur="0.8s"
                         repeatCount="indefinite" />
              </path>
              <circle r="3.5" fill="#ffc266">
                <animateMotion dur="2.6s" repeatCount="indefinite" path={d} />
              </circle>
              <text x={mx} y={my - 7} textAnchor="middle" fill="#ffc266" fontSize="10.5"
                    fontFamily="IBM Plex Mono, monospace">
                {w.id} · {w.eta_minutes}m
              </text>
            </g>
          );
        })}

        {/* Site perimeter — the boundary the geofence watches. Drawn faintly because
            it is context, not an alert, right up until something crosses it. */}
        {(() => {
          const [cx, cy] = project(SITE_CENTER[0], SITE_CENTER[1]);
          // A degree of latitude is ~111 km, and the projection uses one scale for
          // both axes, so the radius converts cleanly to pixels.
          const [, edgeY] = project(SITE_CENTER[0] + SITE_RADIUS_KM / 111, SITE_CENTER[1]);
          const r = Math.abs(cy - edgeY);
          return (
            <g opacity="0.5">
              <circle cx={cx} cy={cy} r={r} fill="none" stroke="#4a5878" strokeWidth="1.2"
                      strokeDasharray="7 6" />
              <text x={cx} y={cy - r - 6} textAnchor="middle" fill="#5d6980" fontSize="9.5"
                    fontFamily="Barlow Condensed, sans-serif" letterSpacing="1.4">
                SITE PERIMETER · {SITE_RADIUS_KM} km
              </text>
            </g>
          );
        })()}

        {/* Technicians */}
        {technicians.map((t) => {
          const [x, y] = project(t.latitude, t.longitude);
          const busy = !t.available;
          return (
            <g key={t.id}>
              <path
                d={`M${x},${y - 6} L${x + 5.5},${y + 4} L${x},${y + 1.5} L${x - 5.5},${y + 4} Z`}
                fill={busy ? "#ffc266" : "#55617a"}
              />
              <text x={x + 9} y={y + 4} fill="#6c7691" fontSize="9.5"
                    fontFamily="Barlow, sans-serif">
                {t.name.split(" ")[0]}
              </text>
            </g>
          );
        })}

        {/* Assets */}
        {assets.map((a) => {
          const [x, y] = project(a.latitude, a.longitude);
          const c = STATE_COLOR[a.state] ?? "#7e8798";
          const sel = a.id === selectedId;
          const alert = a.state === "silent" || a.state === "anomaly";
          const forecast = riskById[a.id];
          const risky = !!forecast;
          return (
            <g className="asset-marker" key={a.id} onClick={() => onSelect(a.id)}>
              {/* The dot is 4.6 units in a 900-wide viewBox — about two pixels once
                  the map is scaled into its panel, which is far too small to hit.
                  This invisible disc is what you actually click. */}
              <circle cx={x} cy={y} r="15" fill="transparent" />
              <title>
                {`${a.id} — ${a.label} (${a.state})` +
                  (forecast
                    ? ` · predicted failure in ~${forecast.horizon_hours ?? "?"}h`
                    : "")}
              </title>
              {alert && (
                <circle cx={x} cy={y} r="8" fill="none" stroke={c} strokeWidth="1.5">
                  <animate attributeName="r" from="6" to="20" dur="1.6s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.7" to="0" dur="1.6s"
                           repeatCount="indefinite" />
                </circle>
              )}
              {/* A forecast, drawn distinctly from a fault. This machine is running
                  normally right now — the dashed ring says the model expects it not
                  to be, which is the difference between the reactive and proactive
                  halves of the system. Without it the map called a machine "healthy"
                  that the predictive panel had just put a day from failure. */}
              {risky && !alert && (
                <circle cx={x} cy={y} r="9" fill="none" stroke="var(--warn, #f0a830)"
                        strokeWidth="1.3" strokeDasharray="2.5 2.5" opacity="0.9" />
              )}
              {a.offsite && (
                <circle cx={x} cy={y} r="10" fill="none" stroke="#5aa9e6" strokeWidth="1.6" />
              )}
              {sel && <circle cx={x} cy={y} r="11" fill="none" stroke="#ff9e2c" strokeWidth="1.5" />}
              <circle cx={x} cy={y} r={sel ? 6 : 4.6} fill={c} stroke="#0a1018" strokeWidth="1.5" />
              {(sel || alert) && (
                <text x={x + 10} y={y + 4} fill="#ece6db" fontSize="10.5"
                      fontFamily="IBM Plex Mono, monospace">
                  {a.id}
                </text>
              )}
            </g>
          );
        })}

        {/* Scale + orientation */}
        <g opacity="0.6">
          <text x={W - PAD} y={PAD - 16} textAnchor="end" fill="#5d6980" fontSize="10"
                fontFamily="Barlow Condensed, sans-serif" letterSpacing="1.6">
            N ↑
          </text>
          <line x1={PAD} y1={H - 20} x2={PAD + scaleBar.px} y2={H - 20} stroke="#5d6980"
                strokeWidth="1.5" />
          <line x1={PAD} y1={H - 24} x2={PAD} y2={H - 16} stroke="#5d6980" strokeWidth="1.5" />
          <line x1={PAD + scaleBar.px} y1={H - 24} x2={PAD + scaleBar.px} y2={H - 16}
                stroke="#5d6980" strokeWidth="1.5" />
          <text x={PAD + scaleBar.px + 8} y={H - 16} fill="#5d6980" fontSize="10"
                fontFamily="IBM Plex Mono, monospace">
            {scaleBar.km} km
          </text>
        </g>
      </svg>

      <div className="map-legend">
        {deadZones.length > 0 && (
          <span>
            <i style={{ background: "#5aa9e6", opacity: 0.5 }} />
            learned dead zone
          </span>
        )}
        {Object.entries(STATE_COLOR).map(([k, v]) => (
          <span key={k}>
            <i style={{ background: v }} />
            {STATE_LABEL[k]}
          </span>
        ))}
        {assets.some((a) => a.offsite) && (
          <span title="Still healthy and reporting — but outside the site perimeter.">
            <i className="ring-solid" />
            left the site
          </span>
        )}
        {Object.keys(riskById).length > 0 && (
          <span title="Running normally now; the forecast model expects a failure.">
            <i className="ring" />
            predicted failure
          </span>
        )}
      </div>
    </div>
  );
}
