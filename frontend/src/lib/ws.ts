import { useEffect, useReducer, useRef, useState } from "react";
import type {
  Asset,
  DeadZone,
  GeofenceAlert,
  Incident,
  Kpis,
  Technician,
  TelemetrySample,
  Warehouse,
  TraceStep,
  WorkOrder,
  WsEvent,
} from "../types";

export interface LiveState {
  /** False until the first snapshot lands. An empty fleet and a fleet that has
      not arrived yet are the same object otherwise, and the difference decides
      whether "Every machine is reporting" is a finding or a guess. */
  ready: boolean;
  assets: Record<string, Asset>;
  technicians: Record<string, Technician>;
  warehouses: Record<string, Warehouse>;
  incidents: Record<string, Incident>;
  trace: Record<string, TraceStep[]>;
  workOrders: Record<string, WorkOrder>;
  latestTelemetry: Record<string, TelemetrySample>;
  kpis: Kpis | null;
  deadZones: DeadZone[];
  geofenceAlerts: Record<string, GeofenceAlert>;
}

const empty: LiveState = {
  ready: false,
  assets: {},
  technicians: {},
  warehouses: {},
  incidents: {},
  trace: {},
  workOrders: {},
  latestTelemetry: {},
  kpis: null,
  deadZones: [],
  geofenceAlerts: {},
};

function reducer(state: LiveState, ev: WsEvent): LiveState {
  switch (ev.type) {
    case "snapshot": {
      const p = ev.payload;
      const assets: Record<string, Asset> = {};
      for (const a of p.assets ?? []) assets[a.id] = a;
      const technicians: Record<string, Technician> = {};
      for (const t of p.technicians ?? []) technicians[t.id] = t;
      const warehouses: Record<string, Warehouse> = {};
      for (const w of p.warehouses ?? []) warehouses[w.id] = w;
      const incidents: Record<string, Incident> = {};
      for (const i of p.incidents ?? []) incidents[i.id] = i;
      const workOrders: Record<string, WorkOrder> = {};
      for (const w of p.work_orders ?? []) workOrders[w.id] = w;
      return {
        ready: true,
        assets,
        technicians,
        warehouses,
        incidents,
        trace: p.trace ?? {},
        workOrders,
        latestTelemetry: p.latest_telemetry ?? {},
        kpis: p.kpis ?? null,
        deadZones: p.dead_zones ?? [],
        geofenceAlerts: Object.fromEntries(
          ((p.geofence_alerts ?? []) as GeofenceAlert[]).map((a) => [a.id, a])
        ),
      };
    }
    // Every branch below casts an untyped payload, and this reducer runs during
    // render: one malformed frame used to throw inside it and take the whole React
    // root down to a white page. A frame we cannot read is a frame we ignore.
    case "telemetry": {
      const s = ev.payload as TelemetrySample | null;
      if (!s?.asset_id) return state;
      return {
        ...state,
        latestTelemetry: { ...state.latestTelemetry, [s.asset_id]: s },
      };
    }
    case "asset_update": {
      const a = ev.payload as Asset | null;
      if (!a?.id) return state;
      return { ...state, assets: { ...state.assets, [a.id]: a } };
    }
    case "incident_update": {
      const i = ev.payload as Incident | null;
      if (!i?.id) return state;
      return { ...state, incidents: { ...state.incidents, [i.id]: i } };
    }
    case "trace_step": {
      const s = ev.payload as TraceStep | null;
      if (!s?.incident_id || typeof s.step !== "number") return state;
      const prev = state.trace[s.incident_id] ?? [];
      // A reconnect replays the full snapshot, and in-flight events can arrive
      // again on top of it. Steps are uniquely numbered per incident, so key on
      // that rather than appending blindly — otherwise the trace shows the same
      // step twice and React warns about duplicate keys.
      const i = prev.findIndex((p) => p.step === s.step);
      const next = i === -1 ? [...prev, s] : prev.map((p, j) => (j === i ? s : p));
      next.sort((a, b) => a.step - b.step);
      return { ...state, trace: { ...state.trace, [s.incident_id]: next } };
    }
    case "work_order": {
      const w = ev.payload as WorkOrder | null;
      if (!w?.id) return state;
      return { ...state, workOrders: { ...state.workOrders, [w.id]: w } };
    }
    case "work_order_deleted": {
      const id = (ev.payload as { id?: string } | null)?.id;
      if (!id) return state;
      const { [id]: _dropped, ...rest } = state.workOrders;
      return { ...state, workOrders: rest };
    }
    case "geofence_alert": {
      const a = ev.payload as GeofenceAlert | null;
      if (!a?.id) return state;
      return { ...state, geofenceAlerts: { ...state.geofenceAlerts, [a.id]: a } };
    }
    case "technicians": {
      // Crews move between jobs and go on and off shift. Without this the map keeps
      // showing wherever they were when the dashboard connected.
      const technicians: Record<string, Technician> = {};
      for (const t of (ev.payload?.technicians ?? []) as Technician[]) technicians[t.id] = t;
      return { ...state, technicians };
    }
    case "warehouses": {
      // Stock moves on every dispatch and every completion, so the depot view and the
      // map markers have to follow it rather than showing what was on the shelf when
      // the dashboard connected.
      const warehouses: Record<string, Warehouse> = {};
      for (const w of (ev.payload?.warehouses ?? []) as Warehouse[]) warehouses[w.id] = w;
      return { ...state, warehouses };
    }
    case "kpis": {
      // A partial object here reaches KpiBar, where `.toFixed` on a missing number
      // is a render-time throw.
      const k = ev.payload as Kpis | null;
      if (!k || typeof k.fleet_size !== "number") return state;
      return { ...state, kpis: k };
    }
    case "dead_zones":
      return { ...state, deadZones: (ev.payload?.zones ?? []) as DeadZone[] };
    default:
      return state;
  }
}

export function useLiveState() {
  const [state, dispatch] = useReducer(reducer, empty);
  const [connected, setConnected] = useState(false);
  const retry = useRef(0);

  // When the last frame arrived. A lid closing or a proxy dropping the tunnel
  // produces a half-open socket that fires neither `onclose` nor `onerror`, so
  // without a watchdog the chip keeps saying "Streaming" over a dashboard that
  // stopped updating minutes ago. That is precisely the failure this product
  // exists to detect, occurring in the product.
  const lastFrame = useRef(Date.now());

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;
    let timer: number | undefined;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        retry.current = 0;
        setConnected(true);
      };
      ws.onclose = () => {
        setConnected(false);
        if (stopped) return;
        const delay = Math.min(1000 * 2 ** retry.current++, 8000);
        timer = window.setTimeout(connect, delay);
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (m) => {
        lastFrame.current = Date.now();
        try {
          dispatch(JSON.parse(m.data) as WsEvent);
        } catch {
          /* ignore malformed frame */
        }
      };
    };
    connect();

    // The backend ticks every 2s and every tick carries technicians and KPIs, so
    // fifteen seconds of silence means the socket is gone whatever it claims.
    // Closing it hands over to the existing backoff reconnect.
    const watchdog = window.setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN && Date.now() - lastFrame.current > 15_000) {
        ws.close();
      }
    }, 5_000);

    return () => {
      stopped = true;
      window.clearInterval(watchdog);
      if (timer) window.clearTimeout(timer);
      if (!ws) return;
      // React StrictMode mounts effects twice in development, so this cleanup can
      // land while the socket is still CONNECTING. Closing then throws a console
      // error and leaves a torn-down socket that still fires onclose, which would
      // trip the reconnect path. Detach handlers first, and only close once open.
      ws.onopen = null;
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      if (ws.readyState === WebSocket.OPEN) ws.close();
      else if (ws.readyState === WebSocket.CONNECTING) {
        const sock = ws;
        sock.addEventListener("open", () => sock.close(), { once: true });
      }
    };
  }, []);

  return { state, connected };
}
