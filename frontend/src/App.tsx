import { useEffect, useMemo, useState } from "react";
import { AgentTrace } from "./components/AgentTrace";
import { AssetDrawer } from "./components/AssetDrawer";
import { FleetHealthPanel } from "./components/FleetHealthPanel";
import { FleetMap } from "./components/FleetMap";
import { IncidentFeed } from "./components/IncidentFeed";
import { KpiBar } from "./components/KpiBar";
import { LiveCamaraPanel } from "./components/LiveCamaraPanel";
import { ScenarioPanel } from "./components/ScenarioPanel";
import { WorkOrderCard } from "./components/WorkOrderCard";
import { getHealth } from "./lib/api";
import { useLiveState } from "./lib/ws";

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

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  const assets = useMemo(() => Object.values(state.assets), [state.assets]);
  const technicians = useMemo(() => Object.values(state.technicians), [state.technicians]);
  const incidents = useMemo(() => Object.values(state.incidents), [state.incidents]);
  const workOrders = useMemo(() => Object.values(state.workOrders), [state.workOrders]);

  // Follow the live incident so the trace shows without anyone clicking.
  useEffect(() => {
    if (incidents.length === 0) return;
    const active = incidents.find((i) => i.closed_at === null);
    if (active) {
      setSelectedIncident(active.id);
      setSelectedAsset(active.asset_id);
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
          <div className="panel">
            <header>
              <h2>Network as Code</h2>
              <span className="note">sandbox</span>
            </header>
            <div className="body">
              <LiveCamaraPanel assetId={selectedAsset} />
            </div>
          </div>
          <div className="panel grow">
            <header>
              <h2>Predictive maintenance</h2>
            </header>
            <div className="body">
              <FleetHealthPanel onSelect={setSelectedAsset} />
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
