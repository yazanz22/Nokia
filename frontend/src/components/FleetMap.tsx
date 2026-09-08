import { memo, useCallback, useId, useMemo, useRef } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import type { Asset, DeadZone, Technician, Warehouse, WorkOrder } from "../types";
import { GROUP_LABEL, minutes, STATE_GROUP, type StateGroup } from "../lib/format";

// The operational site perimeter. SOURCE OF TRUTH: backend/app/nac/base.py
// (SITE_CENTER / SITE_RADIUS_KM). These are copies, deliberately: a browser cannot
// import Python, and the alternative — putting them on the wire in the websocket
// snapshot — would make a fixed geographic constant into a runtime dependency, so the
// perimeter ring could not be drawn until the first frame arrived and every reader
// would need a fallback for a value that has never changed. What made the duplication
// dangerous was that nothing compared the two, so that is what is fixed instead:
// backend/tests/test_no_duplicate_contracts.py reads THIS file and fails if either
// number stops matching the Python. Change them there first.
const SITE_CENTER: [number, number] = [27.5581, 34.9196];
const SITE_RADIUS_KM = 80;

const W = 900;
const H = 640;
const PAD = 46;

// Four colours, one per displayed state group. Every value is themed in
// styles/map.css; nothing here decides an appearance.
const GROUP_COLOR: Record<StateGroup, string> = {
  healthy: "var(--map-healthy)",
  attention: "var(--map-attention)",
  nocoverage: "var(--map-nocoverage)",
  handled: "var(--map-handled)",
};

const LEGEND: StateGroup[] = ["healthy", "attention", "nocoverage", "handled"];

interface Props {
  assets: Asset[];
  technicians: Technician[];
  warehouses: Warehouse[];
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

type Pt = [number, number];

/** Shortest distance between two segments — 0 if they cross. */
function segGap(p: Pt, q: Pt, r: Pt, s: Pt): number {
  const side = (a: Pt, b: Pt, c: Pt) =>
    (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0]);
  if (side(p, r, s) * side(q, r, s) < 0 && side(p, q, r) * side(p, q, s) < 0) return 0;
  const ptSeg = (c: Pt, a: Pt, b: Pt) => {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len = dx * dx + dy * dy;
    const t = len === 0 ? 0 : Math.max(0, Math.min(1, ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / len));
    return Math.hypot(c[0] - (a[0] + t * dx), c[1] - (a[1] + t * dy));
  };
  return Math.min(ptSeg(p, r, s), ptSeg(q, r, s), ptSeg(r, p, q), ptSeg(s, p, q));
}

/** Shortest distance between the boundaries of two convex polygons. */
function polyGap(a: Pt[], b: Pt[]): number {
  let best = Infinity;
  for (let i = 0; i < a.length; i++) {
    for (let j = 0; j < b.length; j++) {
      best = Math.min(best, segGap(a[i], a[(i + 1) % a.length], b[j], b[(j + 1) % b.length]));
      if (best === 0) return 0;
    }
  }
  return best;
}

// The outline is drawn a little outside the machines so it reads as an area rather
// than a join-the-dots, but the padding is a want, not a right: two areas 30 px apart
// cannot both be padded by 22 without meeting in the middle. So the padding is
// whatever the tightest pair of areas can afford, and never more than MAX_INFLATE.
const MAX_INFLATE = 22;
const ZONE_CLEARANCE = 8; // visible gap left between two site outlines, in viewBox units.

// Markers are ~4.6 units wide in a 900-unit viewBox — two screen pixels once the map
// is scaled into its panel, far too small to hit — so each one carries an invisible
// disc you actually click. MAX_HIT is the size that makes a lone machine comfortable;
// in a cluster the disc shrinks instead (see `markers`), with no floor, because any
// floor is a licence to overlap the neighbour again.
const MAX_HIT = 15;
// And a floor, because a disc that shrinks to nothing is not a smaller target, it
// is no target at all: two machines projecting to the same point both got r=0, so
// neither was hit-testable and pickNearest broke the tie by array order, leaving
// the second one permanently unclickable. Below this the discs may overlap, which
// is harmless — pickNearest resolves overlap by true distance anyway.
const MIN_HIT = 3;
// How far from a machine a click still counts as aimed at it, for clicks that land in
// the gaps between discs. Beyond this the map is empty desert and nothing is selected.
const PICK_RADIUS = 34;

function FleetMapImpl({
  assets,
  technicians,
  warehouses,
  workOrders,
  deadZones,
  riskById = {},
  selectedId,
  onSelect,
}: Props) {
  // Equirectangular with a single scale for both axes. Stretching each axis
  // independently to fill the box makes the map lie about distance — at this latitude
  // it rendered east-west spans 1.85x larger than north-south ones, so a technician
  // who looked closer often was not. "Nearest" has to mean the same thing on the map
  // as it does in the dispatch.
  const project = useMemo(() => {
    const pts = [...assets, ...technicians, ...warehouses];
    if (pts.length === 0) return () => [W / 2, H / 2] as [number, number];
    const lats = pts.map((p) => p.latitude);
    const lons = pts.map((p) => p.longitude);
    // Quantised to a ~5 km grid. The extent is taken from the crew as well as the
    // machines, and the simulator nudges every available technician a fraction of a
    // degree on each 2s tick; whenever one of them held the extreme in any
    // direction the whole frame re-fitted, which moved every marker on the map,
    // the stationary depots and the perimeter ring with it, and changed the scale
    // bar. The map crept and shimmered continuously and nothing was ever where you
    // last looked. It now re-fits only when something genuinely leaves the box,
    // which is the one time you want it to.
    const q = (v: number) => Math.round(v * 20) / 20;
    const latLo = q(Math.min(...lats) - 0.05);
    const latHi = q(Math.max(...lats) + 0.05);
    const lonLo = q(Math.min(...lons) - 0.05);
    const lonHi = q(Math.max(...lons) + 0.05);

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
  }, [assets, technicians, warehouses]);

  // Site zones are genuine, and now they are also geographic: the backend assigns a
  // machine to the working area it is nearest to (seed.py::_SITE_AREAS), which is a
  // Voronoi partition — convex, disjoint cells. The convex hull of the machines inside
  // one convex cell stays inside that cell, so these outlines cannot cross. They used
  // to, badly: sites were handed out by hashing the asset id, so all five hulls covered
  // the whole map and two of the labels landed on top of each other.
  //
  // A machine that has driven off the site (the geofence beat does exactly that) is
  // left out. It has not taken its working area with it, and including it stretched
  // one hull clear across the map mid-demo.
  const zones = useMemo(() => {
    const bySite = new Map<string, [number, number][]>();
    for (const a of assets) {
      if (a.offsite) continue;
      const p = project(a.latitude, a.longitude);
      const arr = bySite.get(a.site) ?? [];
      arr.push(p);
      bySite.set(a.site, arr);
    }
    const raw = [...bySite.entries()]
      .filter(([, pts]) => pts.length >= 3)
      .map(([site, pts]) => ({ site, poly: hull(pts) }));

    // Pad by half of what the closest pair of areas can spare, so no amount of
    // padding can ever make two outlines touch.
    let gap = Infinity;
    for (let i = 0; i < raw.length; i++) {
      for (let j = i + 1; j < raw.length; j++) {
        gap = Math.min(gap, polyGap(raw[i].poly, raw[j].poly));
      }
    }
    const by = Number.isFinite(gap)
      ? Math.max(0, Math.min(MAX_INFLATE, (gap - ZONE_CLEARANCE) / 2))
      : MAX_INFLATE;

    return raw.map(({ site, poly: base }) => {
      const poly = inflate(base, by);
      const cx = poly.reduce((s, p) => s + p[0], 0) / poly.length;
      const cy = poly.reduce((s, p) => s + p[1], 0) / poly.length;
      return { site, d: poly.map((p) => p.join(",")).join(" "), cx, cy };
    });
  }, [assets, project]);

  // Every marker's position, and the size of the disc that catches its clicks. A flat
  // r=15 on all thirty was wrong: at this density the discs overlapped, and SVG
  // hit-testing hands the click to the topmost element, so clicking a machine inside a
  // cluster selected whichever of its neighbours happened to be drawn last. Sizing each
  // disc to half the distance to its nearest neighbour keeps overlap to the cases
  // clamped by MIN_HIT, and pickNearest resolves those by true distance, so the
  // machine you select is always the nearest one either way.
  const markers = useMemo(() => {
    const pts = assets.map((a) => project(a.latitude, a.longitude));
    return assets.map((a, i) => {
      let nearest = Infinity;
      for (let j = 0; j < pts.length; j++) {
        if (j === i) continue;
        nearest = Math.min(nearest, Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]));
      }
      const hit = Number.isFinite(nearest)
        ? Math.max(MIN_HIT, Math.min(MAX_HIT, nearest / 2))
        : MAX_HIT;
      return { id: a.id, x: pts[i][0], y: pts[i][1], hit };
    });
  }, [assets, project]);

  const svgRef = useRef<SVGSVGElement | null>(null);

  // The reduce-motion block in base.css neutralises CSS animations. SMIL is not a
  // CSS animation, so the alert pulse, the marching route dashes and the travelling
  // dot all kept running for somebody who had asked for no motion — continuous
  // large-area movement on the biggest panel in the product, which is exactly the
  // case the setting exists for. Read once: a viewer who changes the OS setting
  // mid-session gets it on the next mount, which is the right trade for not
  // subscribing every marker to a media query.
  const still = useMemo(
    () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
    []
  );

  // Ids in <defs> are document-global. Only one map mounts today, but a second one
  // would silently share the first's gradients and patterns.
  const uid = useId().replace(/:/g, "");

  // Shrinking the discs leaves gaps between them, and a click that lands in a gap
  // should still pick the machine it was aimed at rather than nothing at all. This
  // catches those: it converts the click into viewBox units (getScreenCTM handles the
  // preserveAspectRatio="slice" crop) and takes the nearest machine within PICK_RADIUS.
  const pickNearest = useCallback(
    (e: ReactMouseEvent<SVGRectElement>) => {
      const ctm = svgRef.current?.getScreenCTM();
      if (!ctm) return;
      const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
      let best: string | null = null;
      let bestD = PICK_RADIUS;
      for (const m of markers) {
        const d = Math.hypot(m.x - p.x, m.y - p.y);
        if (d < bestD) {
          bestD = d;
          best = m.id;
        }
      }
      if (best) onSelect(best);
    },
    [markers, onSelect],
  );

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
      {/* `meet`, not `slice`. The panel is never the viewBox's 1.4:1, and covering
          it cropped whatever did not fit: about 20 units top and bottom at 1440
          wide, and roughly half the site left and right in the single-column
          layout, where machines near the edge became invisible AND unclickable.
          The projection already insets everything to PAD, so letterboxing shows
          empty desert rather than losing content. */}
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet"
           role="group" aria-label="Fleet map of the project site">
        <defs>
          <radialGradient id={`terrain-${uid}`} cx="42%" cy="34%" r="78%">
            <stop offset="0%" stopColor="var(--map-terrain-1)" />
            <stop offset="55%" stopColor="var(--map-terrain-2)" />
            <stop offset="100%" stopColor="var(--map-terrain-3)" />
          </radialGradient>
          <pattern id={`grid-${uid}`} width="45" height="45" patternUnits="userSpaceOnUse">
            <path d="M45 0H0V45" fill="none" stroke="var(--map-grid)" strokeWidth="1" />
          </pattern>
          <filter id={`soft-${uid}`} x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="9" />
          </filter>
          <pattern id={`deadzone-${uid}`} width="7" height="7" patternUnits="userSpaceOnUse"
                   patternTransform="rotate(45)">
            <rect width="7" height="7" fill="var(--map-nocoverage)" opacity="0.07" />
            <line x1="0" y1="0" x2="0" y2="7" stroke="var(--map-nocoverage)" strokeWidth="1.4"
                  opacity="0.3" />
          </pattern>
        </defs>

        <rect width={W} height={H} fill={`url(#terrain-${uid})`} />
        <rect width={W} height={H} fill={`url(#grid-${uid})`} opacity="0.55" />

        {/* Contour suggestion — desert relief, purely atmospheric. */}
        <g stroke="var(--map-contour)" fill="none" opacity="0.6">
          <path d="M-20 190 Q 190 130 380 200 T 780 175 T 960 215" strokeWidth="1" />
          <path d="M-20 250 Q 200 195 400 258 T 800 232 T 960 268" strokeWidth="1" />
          <path d="M-20 430 Q 230 372 450 438 T 850 408 T 960 442" strokeWidth="1" />
          <path d="M-20 496 Q 240 440 460 502 T 860 472 T 960 506" strokeWidth="1" />
        </g>

        {/* Coverage the agent has learned is bad. Nobody surveyed for this — it is
            the by-product of investigating incidents, drawn where they clustered. */}
        {deadZones.map((z, zi) => {
          const [x1, y1] = project(z.latitude + z.span / 2, z.longitude - z.span / 2);
          const [x2, y2] = project(z.latitude - z.span / 2, z.longitude + z.span / 2);
          const w = Math.max(Math.abs(x2 - x1), 26);
          const h = Math.max(Math.abs(y2 - y1), 26);
          return (
            <g key={`dz-${zi}-${z.latitude}-${z.longitude}`}>
              <rect x={Math.min(x1, x2)} y={Math.min(y1, y2)} width={w} height={h}
                    fill={`url(#deadzone-${uid})`} stroke="var(--map-nocoverage)" strokeWidth="1"
                    strokeDasharray="4 3" opacity="0.85" rx="3" />
              <text x={Math.min(x1, x2) + w / 2} y={Math.min(y1, y2) - 5} textAnchor="middle"
                    fill="var(--map-nocoverage)" fontSize="10"
                    fontFamily="var(--font-sans)" fontWeight="500">
                Known dead zone ({z.incidents})
              </text>
            </g>
          );
        })}

        {/* Site working areas */}
        {zones.map((z) => (
          <g key={z.site}>
            <polygon points={z.d} fill="var(--map-zone-fill)" opacity="0.6" filter={`url(#soft-${uid})`} />
            <polygon
              points={z.d}
              fill="none"
              stroke="var(--map-zone-line)"
              strokeWidth="1"
              strokeDasharray="3 4"
            />
            <text
              x={z.cx}
              y={z.cy}
              textAnchor="middle"
              fill="var(--map-label)"
              fontSize="10.5"
              fontFamily="var(--font-sans)"
              fontWeight="500"
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
              <path d={d} fill="none" stroke="var(--map-route)" strokeWidth="1.6" opacity="0.55"
                    strokeDasharray="6 5">
                {!still && (
                  <animate attributeName="stroke-dashoffset" from="11" to="0" dur="0.8s"
                           repeatCount="indefinite" />
                )}
              </path>
              {!still && (
                <circle r="3.5" fill="var(--map-route)">
                  <animateMotion dur="2.6s" repeatCount="indefinite" path={d} />
                </circle>
              )}
              <text x={mx} y={my - 7} textAnchor="middle" fill="var(--map-route)" fontSize="10"
                    fontFamily="var(--font-mono)">
                {w.id} {minutes(w.eta_minutes)}
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
              <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--map-zone-line)"
                      strokeWidth="1.2" strokeDasharray="7 6" />
              <text x={cx} y={cy - r - 6} textAnchor="middle" fill="var(--map-label)"
                    fontSize="10" fontFamily="var(--font-sans)" fontWeight="500">
                Site perimeter
              </text>
            </g>
          );
        })()}

        {/* Clicks that land between the hit discs — see pickNearest. It has to sit
            ABOVE the zones (whose polygons would otherwise swallow the click and
            have no handler) and BELOW everything with its own tooltip or hit disc.
            It was last, over the depots and the crew: `fill="transparent"` is
            painted, so it captured every pointer event on them. Depot stock lives
            only in that <title>, so it was unreachable, and clicking a depot
            selected whichever machine happened to be nearest. */}
        <rect width={W} height={H} fill="transparent" onClick={pickNearest} />

        {/* Parts depots. A square, not a fifth colour: a depot is a different kind
            of thing from a machine, and shape carries that without spending a legend
            entry on it. Drawn under the crew and the machines because it never moves
            and never needs attention. */}
        {warehouses.map((wh) => {
          const [x, y] = project(wh.latitude, wh.longitude);
          const held = Object.values(wh.stock).reduce((s, n) => s + n, 0);
          return (
            <g
              className="depot-marker"
              key={wh.id}
              role="img"
              aria-label={`${wh.name}, parts depot, ${held} units in stock`}
            >
              <title>{`${wh.name} - ${held} units in stock`}</title>
              {/* Mark only, no label. There are two of them, they never move, and
                  their names are long: printed on the map they collided with the
                  working-area labels and added two of the longest strings on a
                  surface that is read at a glance. The key top-left says what a
                  square is; the name is in the title and the accessible name. */}
              <rect x={x - 5} y={y - 5} width="10" height="10" rx="2" />
            </g>
          );
        })}

        {/* Technicians */}
        {technicians.map((t) => {
          const [x, y] = project(t.latitude, t.longitude);
          const busy = !t.available;
          return (
            <g
              key={t.id}
              role="img"
              aria-label={`${t.name}, technician, ${busy ? "on a job" : "available"}`}
            >
              <path
                d={`M${x},${y - 6} L${x + 5.5},${y + 4} L${x},${y + 1.5} L${x - 5.5},${y + 4} Z`}
                fill={busy ? "var(--map-tech-busy)" : "var(--map-tech)"}
              />
              <text x={x + 9} y={y + 4} fill="var(--map-label)" fontSize="11"
                    fontFamily="var(--font-sans)">
                {t.name.split(" ")[0]}
              </text>
            </g>
          );
        })}

        {/* Assets */}
        {assets.map((a, i) => {
          const { x, y, hit } = markers[i];
          const group = STATE_GROUP[a.state] ?? "healthy";
          const c = GROUP_COLOR[group];
          const sel = a.id === selectedId;
          const alert = group === "attention";
          const forecast = riskById[a.id];
          const risky = !!forecast;
          const description =
            `${a.id}, ${a.label}. ${GROUP_LABEL[group]}` +
            (a.offsite ? ". Outside the site perimeter" : "") +
            (forecast?.horizon_hours != null
              ? `. Failure forecast in about ${forecast.horizon_hours} hours`
              : "");
          return (
            <g
              className="asset-marker"
              key={a.id}
              role="button"
              tabIndex={0}
              aria-label={description}
              aria-current={sel ? "true" : undefined}
              onClick={() => onSelect(a.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
                  // Space scrolls the page otherwise, which throws the map off screen
                  // in the middle of tabbing through the fleet.
                  e.preventDefault();
                  onSelect(a.id);
                }
              }}
            >
              {/* The dot is 4.6 units in a 900-wide viewBox — about two pixels once
                  the map is scaled into its panel, which is far too small to hit.
                  This invisible disc is what you actually click, and what shows the
                  focus ring when you tab to the machine instead. */}
              <circle className="marker-hit" cx={x} cy={y} r={hit} fill="transparent" />
              <title>{description}</title>
              {alert && (
                <circle cx={x} cy={y} r={still ? 12 : 8} fill="none" stroke={c}
                        strokeWidth="1.5" opacity={still ? 0.6 : 1}>
                  {!still && (
                    <>
                      <animate attributeName="r" from="6" to="20" dur="1.6s"
                               repeatCount="indefinite" />
                      <animate attributeName="opacity" from="0.7" to="0" dur="1.6s"
                               repeatCount="indefinite" />
                    </>
                  )}
                </circle>
              )}
              {/* A forecast, drawn distinctly from a fault. This machine is running
                  normally right now — the dashed ring says the model expects it not
                  to be, which is the difference between the reactive and proactive
                  halves of the system. Without it the map called a machine "healthy"
                  that the predictive panel had just put a day from failure. */}
              {risky && !alert && (
                <circle cx={x} cy={y} r="9" fill="none" stroke="var(--map-handled)"
                        strokeWidth="1.3" strokeDasharray="2.5 2.5" opacity="0.9" />
              )}
              {a.offsite && (
                <circle cx={x} cy={y} r="10" fill="none" stroke="var(--map-nocoverage)"
                        strokeWidth="1.6" />
              )}
              {sel && (
                <circle cx={x} cy={y} r="11" fill="none" stroke="var(--accent)" strokeWidth="1.8" />
              )}
              <circle cx={x} cy={y} r={sel ? 6 : 4.6} fill={c}
                      stroke="var(--map-marker-stroke)" strokeWidth="1.5" />
              {(sel || alert) && (
                <text x={x + 10} y={y + 4} fill="var(--text)" fontSize="10"
                      fontFamily="var(--font-mono)">
                  {a.id}
                </text>
              )}
            </g>
          );
        })}

        {/* Scale + orientation */}
        <g opacity="0.6">
          <text x={W - PAD} y={PAD - 16} textAnchor="end" fill="var(--map-label)" fontSize="11"
                fontFamily="var(--font-sans)" fontWeight="500">
            N
          </text>
          <line x1={PAD} y1={H - 20} x2={PAD + scaleBar.px} y2={H - 20}
                stroke="var(--map-label)" strokeWidth="1.5" />
          <line x1={PAD} y1={H - 24} x2={PAD} y2={H - 16} stroke="var(--map-label)"
                strokeWidth="1.5" />
          <line x1={PAD + scaleBar.px} y1={H - 24} x2={PAD + scaleBar.px} y2={H - 16}
                stroke="var(--map-label)" strokeWidth="1.5" />
          <text x={PAD + scaleBar.px + 8} y={H - 16} fill="var(--map-label)" fontSize="10"
                fontFamily="var(--font-mono)">
            {scaleBar.km} km
          </text>
        </g>
      </svg>

      {/* What the glyphs are. Separate from the colour key bottom-right, and in the
          opposite corner, because they answer different questions: this one is what
          kind of thing a mark is, that one is what state a machine is in. */}
      <div className="map-key">
        <span>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden focusable="false">
            <path d="M6,1 L11.5,11 L6,8.5 L0.5,11 Z" fill="var(--map-tech)" />
          </svg>
          Technician
        </span>
        <span>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden focusable="false">
            <rect x="1" y="1" width="10" height="10" rx="2" fill="var(--map-depot)" />
          </svg>
          Parts depot
        </span>
      </div>

      {/* Four entries. The dead-zone, off-site and forecast rings used to have
          their own swatches, which made an eight-item legend for a map somebody
          glances at. Those three are labelled on the map itself where they occur,
          so the legend only has to carry the thing every dot has: its state. */}
      <div className="map-legend">
        {LEGEND.map((g) => (
          <span key={g}>
            <i className={`is-${g}`} />
            {GROUP_LABEL[g]}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Memoised. ~62 websocket frames arrive per 2s tick, each in its own task, so
 * React cannot batch them: the map was reconciling 500+ SVG nodes about thirty
 * times a second. Every prop it takes is already reference-stable across
 * telemetry frames, so this skips the work entirely on the frames that cannot
 * change what it draws.
 */
export const FleetMap = memo(FleetMapImpl);
