import { useEffect, useMemo, useRef, useState } from "react";
import { AgentTrace } from "./components/AgentTrace";
import { AssetDrawer } from "./components/AssetDrawer";
import { FleetHealthPanel } from "./components/FleetHealthPanel";
import { FleetMap } from "./components/FleetMap";
import { IncidentFeed } from "./components/IncidentFeed";
import { KpiBar } from "./components/KpiBar";
import { LiveCamaraPanel } from "./components/LiveCamaraPanel";
import { ScenarioPanel } from "./components/ScenarioPanel";
import { WorkOrderCard } from "./components/WorkOrderCard";
import { getFleetHealth, getHealth } from "./lib/api";
import { useLiveState } from "./lib/ws";
import type { RiskRow } from "./types";

interface Health {
  nac_mode: string;
  live_camara_available: boolean;
  agent_mode: string;
  llm_model: string | null;
  ml_backend: string;
}

export default function App() {
  const { state, connected } = useLiveState();
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  // The live sandbox panel is proof, not a working surface — it earns its space during
  // the API part of a demo and is in the way for the rest of it.
  const [nacOpen, setNacOpen] = useState(true);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  // Fetched here rather than inside the predictive panel so the map can draw the
  // same forecast. A machine can be streaming perfectly and still be a day from a
  // bearing failure; showing that only in a side panel made the map say "healthy"
  // about a machine the tool had just called critical.
  const [risk, setRisk] = useState<RiskRow[]>([]);
  const [riskAvailable, setRiskAvailable] = useState(true);
  const [atRisk, setAtRisk] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      getFleetHealth()
        .then((d) => {
          if (cancelled) return;
          setRiskAvailable(d.available);
          setAtRisk(d.at_risk ?? 0);
          setRisk(d.assets ?? []);
        })
        .catch(() => setRiskAvailable(false));
    load();
    // Forecasts move as the fleet does; loading once left a snapshot from whenever
    // the tab happened to open.
    const timer = window.setInterval(load, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const riskById = useMemo(() => {
    const m: Record<string, RiskRow> = {};
    for (const r of risk) if (r.at_risk) m[r.asset_id] = r;
    return m;
  }, [risk]);

  const assets = useMemo(() => Object.values(state.assets), [state.assets]);
  const technicians = useMemo(() => Object.values(state.technicians), [state.technicians]);
  const incidents = useMemo(() => Object.values(state.incidents), [state.incidents]);
  const workOrders = useMemo(() => Object.values(state.workOrders), [state.workOrders]);
  const geofenceAlerts = useMemo(
    () =>
      Object.values(state.geofenceAlerts).sort((a, b) => b.at.localeCompare(a.at)),
    [state.geofenceAlerts]
  );

  // Which incident the view has already jumped to on its own. Without this the
  // effect below re-selects on every incident update — and since an investigation
  // emits a stream of them, anything the operator clicked was yanked back within
  // a second. Selecting a machine simply did not work while the agent was busy.
  const followed = useRef<string | null>(null);

  // Follow the live incident so the trace shows without anyone clicking — but only
  // when it is genuinely new. A machine going dark should take over the screen; an
  // investigation already on screen should not keep stealing it back.
  useEffect(() => {
    if (incidents.length === 0) return;
    const active = incidents.find((i) => i.closed_at === null);
    if (active) {
      if (followed.current !== active.id) {
        followed.current = active.id;
        setSelectedIncident(active.id);
        setSelectedAsset(active.asset_id);
      }
      return;
    }
    setSelectedIncident((cur) => {
      if (cur) return cur;
      return [...incidents].sort((a, b) => b.opened_at.localeCompare(a.opened_at))[0]?.id ?? null;
    });
  }, [incidents]);

  const traceIncidentId =
    selectedIncident ??
    [...incidents].sort((a, b) => b.opened_at.localeCompare(a.opened_at))[0]?.id ??
    null;
  const traceSteps = traceIncidentId ? state.trace[traceIncidentId] ?? [] : [];
  const traceIncident = traceIncidentId ? state.incidents[traceIncidentId] : undefined;
  const investigating = traceIncident?.closed_at === null;
  const traceWorkOrders = workOrders.filter((w) => w.incident_id === traceIncidentId);
  const shownWorkOrders = traceWorkOrders.length ? traceWorkOrders : workOrders;

  const asset = selectedAsset ? state.assets[selectedAsset] ?? null : null;

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark">FI</div>
          <div className="brand-text">
            <h1>Asset Sentinel</h1>
            <div className="sub">
              Autonomous fleet diagnostics · CAMARA Device Status + Location Retrieval via Nokia
              Network as Code
            </div>
          </div>
        </div>

        <div className="chips">
          {health && (
            <>
              <span className="chip">
                agent <b>{health.agent_mode === "llm" ? "LLM" : "rule"}</b>
              </span>
              {health.agent_mode === "llm" && health.llm_model && (
                <span className="chip">{health.llm_model.replace("groq:", "")}</span>
              )}
              <span className="chip">
                ML <b>{health.ml_backend}</b>
              </span>
              <span className={`chip ${health.live_camara_available ? "live" : "off"}`}>
                CAMARA <b>{health.live_camara_available ? "live" : "mock"}</b>
              </span>
            </>
          )}
          <span className={`chip ${connected ? "live" : "off"}`}>
            <span className="pulse" />
            {connected ? "streaming" : "reconnecting"}
          </span>
        </div>
      </div>

      <KpiBar kpis={state.kpis} />

      <div className="grid">
        {/* ── hero: the site ─────────────────────────────────────────── */}
        <div className="col">
          <div className="panel feature grow">
            <header>
              <h2>Site map</h2>
              <span className="note">{assets.length} assets · NEOM / Gulf of Aqaba</span>
            </header>
            <FleetMap
              assets={assets}
              technicians={technicians}
              workOrders={workOrders}
              deadZones={state.deadZones}
              riskById={riskById}
              selectedId={selectedAsset}
              onSelect={setSelectedAsset}
            />
          </div>
          <div className="panel" style={{ maxHeight: "28%" }}>
            <header>
              <h2>Asset telemetry</h2>
            </header>
            <div className="body">
              <AssetDrawer
                asset={asset}
                risk={selectedAsset ? riskById[selectedAsset] ?? null : null}
                history={selectedAsset ? state.telemetryHistory[selectedAsset] ?? [] : []}
                latest={selectedAsset ? state.latestTelemetry[selectedAsset] ?? null : null}
              />
            </div>
          </div>
        </div>

        {/* ── controls & foresight ───────────────────────────────────── */}
        <div className="col">
          <div className="panel">
            <header>
              <h2>Simulate</h2>
            </header>
            <div className="body">
              <ScenarioPanel assets={assets} />
            </div>
          </div>
          <div className={`panel${nacOpen ? "" : " collapsed"}`}>
            <header>
              <h2>Network as Code</h2>
              <span className="note">sandbox</span>
              <button
                className="panel-toggle"
                onClick={() => setNacOpen((v) => !v)}
                aria-expanded={nacOpen}
                title={nacOpen ? "Minimise panel" : "Expand panel"}
              >
                {nacOpen ? "−" : "+"}
              </button>
            </header>
            {nacOpen && (
              <div className="body">
                <LiveCamaraPanel assetId={selectedAsset} />
              </div>
            )}
          </div>
          <div className="panel grow">
            <header>
              <h2>Predictive maintenance</h2>
            </header>
            <div className="body">
              <FleetHealthPanel
                rows={risk}
                available={riskAvailable}
                atRisk={atRisk}
                onSelect={setSelectedAsset}
              />
            </div>
          </div>
        </div>

        {/* ── the agent, and what it decided ─────────────────────────── */}
        <div className="col col-trace">
          <div className="panel feature grow">
            <header>
              <h2>Agent reasoning</h2>
              {traceIncidentId && <span className="note">{traceIncidentId}</span>}
            </header>
            <div className="body">
              <AgentTrace steps={traceSteps} active={!!investigating} />
            </div>
          </div>
          <div className="panel" style={{ flex: "0 0 auto", maxHeight: "40%" }}>
            <header>
              <h2>Work orders</h2>
            </header>
            <div className="body">
              {shownWorkOrders.length === 0 ? (
                <div className="empty">
                  <strong>None issued</strong>
                  <span>
                    A work order is only raised once the network has been ruled out as the cause.
                  </span>
                </div>
              ) : (
                shownWorkOrders.map((w) => <WorkOrderCard key={w.id} wo={w} />)
              )}
            </div>
          </div>
          <div className="panel" style={{ flex: "0 0 auto", maxHeight: "30%" }}>
            <header>
              <h2>Incidents</h2>
            </header>
            <div className="body">
              {geofenceAlerts.map((a) => (
                <div className="gf-alert" key={a.id}>
                  <div className="gf-top">
                    <span className="gf-id">{a.id}</span>
                    <span className="gf-tag">perimeter · no fault</span>
                  </div>
                  <div className="gf-body">
                    <b>{a.asset_label || a.asset_id}</b> has crossed the site perimeter, heading
                    west toward Egyptian coverage across the Gulf.
                    {a.distance_km >= 1 ? ` Now ${a.distance_km.toFixed(0)} km beyond it.` : ""} It
                    is still healthy and still reporting — which is the point. Flagged on the way
                    out, rather than diagnosed after it goes dark.
                  </div>
                </div>
              ))}
              <IncidentFeed
                incidents={incidents}
                selectedId={selectedIncident}
                onSelect={setSelectedIncident}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
