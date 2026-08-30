import { useEffect, useReducer, useRef, useState } from "react";
import type {
  Asset,
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
      return {
        ...state,
        trace: { ...state.trace, [s.incident_id]: [...prev, s] },
      };
    }
    case "work_order": {
      const w = ev.payload as WorkOrder;
      return { ...state, workOrders: { ...state.workOrders, [w.id]: w } };
    }
    case "kpis":
      return { ...state, kpis: ev.payload as Kpis };
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
      ws?.close();
    };
  }, []);

  return { state, connected };
}
