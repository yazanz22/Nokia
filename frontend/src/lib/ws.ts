import { useEffect, useReducer, useRef, useState } from "react";
import type {
  Asset,
  DeadZone,
  GeofenceAlert,
  Incident,
  Kpis,
  Technician,
  TelemetrySample,
  TraceStep,
  WorkOrder,
  WsEvent,
} from "../types";

export interface LiveState {
  assets: Record<string, Asset>;
  technicians: Record<string, Technician>;
  incidents: Record<string, Incident>;
  trace: Record<string, TraceStep[]>;
  workOrders: Record<string, WorkOrder>;
  latestTelemetry: Record<string, TelemetrySample>;
  telemetryHistory: Record<string, TelemetrySample[]>;
  kpis: Kpis | null;
  deadZones: DeadZone[];
  geofenceAlerts: Record<string, GeofenceAlert>;
}

const HISTORY_CAP = 48;

const empty: LiveState = {
  assets: {},
  technicians: {},
  incidents: {},
  trace: {},
  workOrders: {},
  latestTelemetry: {},
  telemetryHistory: {},
  kpis: null,
  deadZones: [],
  geofenceAlerts: {},
};

function pushHistory(
  hist: Record<string, TelemetrySample[]>,
  s: TelemetrySample
): Record<string, TelemetrySample[]> {
  const prev = hist[s.asset_id] ?? [];
  const next = [...prev, s].slice(-HISTORY_CAP);
  return { ...hist, [s.asset_id]: next };
}

function reducer(state: LiveState, ev: WsEvent): LiveState {
  switch (ev.type) {
    case "snapshot": {
      const p = ev.payload;
      const assets: Record<string, Asset> = {};
      for (const a of p.assets ?? []) assets[a.id] = a;
      const technicians: Record<string, Technician> = {};
      for (const t of p.technicians ?? []) technicians[t.id] = t;
      const incidents: Record<string, Incident> = {};
      for (const i of p.incidents ?? []) incidents[i.id] = i;
      const workOrders: Record<string, WorkOrder> = {};
      for (const w of p.work_orders ?? []) workOrders[w.id] = w;
      return {
        assets,
        technicians,
        incidents,
        trace: p.trace ?? {},
        workOrders,
        latestTelemetry: p.latest_telemetry ?? {},
        telemetryHistory: {},
        kpis: p.kpis ?? null,
        deadZones: p.dead_zones ?? [],
        geofenceAlerts: Object.fromEntries(
          ((p.geofence_alerts ?? []) as GeofenceAlert[]).map((a) => [a.id, a])
        ),
      };
    }
    case "telemetry": {
      const s = ev.payload as TelemetrySample;
      return {
        ...state,
        latestTelemetry: { ...state.latestTelemetry, [s.asset_id]: s },
        telemetryHistory: pushHistory(state.telemetryHistory, s),
      };
    }
    case "asset_update": {
      const a = ev.payload as Asset;
      return { ...state, assets: { ...state.assets, [a.id]: a } };
    }
    case "incident_update": {
      const i = ev.payload as Incident;
      return { ...state, incidents: { ...state.incidents, [i.id]: i } };
    }
    case "trace_step": {
      const s = ev.payload as TraceStep;
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
      const w = ev.payload as WorkOrder;
      return { ...state, workOrders: { ...state.workOrders, [w.id]: w } };
    }
    case "work_order_deleted": {
      const id = (ev.payload as { id: string }).id;
      const { [id]: _dropped, ...rest } = state.workOrders;
      return { ...state, workOrders: rest };
    }
    case "geofence_alert": {
      const a = ev.payload as GeofenceAlert;
      return { ...state, geofenceAlerts: { ...state.geofenceAlerts, [a.id]: a } };
    }
    case "technicians": {
      // Crews move between jobs and go on and off shift. Without this the map keeps
      // showing wherever they were when the dashboard connected.
      const technicians: Record<string, Technician> = {};
      for (const t of (ev.payload?.technicians ?? []) as Technician[]) technicians[t.id] = t;
      return { ...state, technicians };
    }
    case "kpis":
      return { ...state, kpis: ev.payload as Kpis };
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
        try {
          dispatch(JSON.parse(m.data) as WsEvent);
        } catch {
          /* ignore malformed frame */
        }
      };
    };
    connect();

    return () => {
      stopped = true;
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
