import { useEffect, useMemo, useState } from "react";
import { AgentTrace } from "./components/AgentTrace";
import { AssetDrawer } from "./components/AssetDrawer";
import { FleetMap } from "./components/FleetMap";
import { IncidentFeed } from "./components/IncidentFeed";
import { KpiBar } from "./components/KpiBar";
import { LiveCamaraPanel } from "./components/LiveCamaraPanel";
import { ScenarioPanel } from "./components/ScenarioPanel";
import { WorkOrderCard } from "./components/WorkOrderCard";
import { useLiveState } from "./lib/ws";

export default function App() {
  const { state, connected } = useLiveState();
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<string | null>(null);

  const assets = useMemo(() => Object.values(state.assets), [state.assets]);
  const technicians = useMemo(() => Object.values(state.technicians), [state.technicians]);
  const incidents = useMemo(() => Object.values(state.incidents), [state.incidents]);
  const workOrders = useMemo(() => Object.values(state.workOrders), [state.workOrders]);

  // Auto-follow the newest incident so the agent trace shows without a click.
  useEffect(() => {
    if (incidents.length === 0) return;
    const newest = [...incidents].sort((a, b) => b.opened_at.localeCompare(a.opened_at))[0];
    setSelectedIncident((cur) => cur ?? newest.id);
    const active = incidents.find((i) => i.closed_at === null);
    if (active) {
      setSelectedIncident(active.id);
      setSelectedAsset(active.asset_id);
    }
  }, [incidents]);

  const traceIncidentId =
    selectedIncident ??
    [...incidents].sort((a, b) => b.opened_at.localeCompare(a.opened_at))[0]?.id ??
    null;
  const traceSteps = traceIncidentId ? state.trace[traceIncidentId] ?? [] : [];
  const traceWorkOrders = workOrders.filter((w) => w.incident_id === traceIncidentId);

  const asset = selectedAsset ? state.assets[selectedAsset] ?? null : null;

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">
          <h1>FILO Asset Sentinel</h1>
          <span className="sub">
            Dynamic IoT Asset Analytics for Giga-Projects · CAMARA Device Status + Location Retrieval
            via Nokia Network as Code
          </span>
        </div>
        <div className="conn">
          <span className={`dot ${connected ? "on" : ""}`} />
          {connected ? "live" : "reconnecting…"}
        </div>
      </div>

      <KpiBar kpis={state.kpis} />

      <div className="grid">
        <div className="col">
          <div className="panel grow">
            <h2>Fleet map</h2>
            <FleetMap
              assets={assets}
              technicians={technicians}
              workOrders={workOrders}
              selectedId={selectedAsset}
              onSelect={setSelectedAsset}
            />
          </div>
          <div className="panel" style={{ maxHeight: "38%" }}>
            <h2>Asset telemetry</h2>
            <div className="body">
              <AssetDrawer
                asset={asset}
                history={selectedAsset ? state.telemetryHistory[selectedAsset] ?? [] : []}
                latest={selectedAsset ? state.latestTelemetry[selectedAsset] ?? null : null}
              />
            </div>
          </div>
        </div>

        <div className="col">
          <div className="panel">
            <h2>Scenario control</h2>
            <div className="body">
              <ScenarioPanel assets={assets} />
            </div>
          </div>
          <div className="panel">
            <h2>Nokia Network as Code · live</h2>
            <div className="body">
              <LiveCamaraPanel assetId={selectedAsset} />
            </div>
          </div>
          <div className="panel grow">
            <h2>Incident feed</h2>
            <div className="body">
              <IncidentFeed
                incidents={incidents}
                selectedId={selectedIncident}
                onSelect={setSelectedIncident}
              />
            </div>
          </div>
        </div>

        <div className="col">
          <div className="panel grow">
            <h2>Agent reasoning trace {traceIncidentId ? `· ${traceIncidentId}` : ""}</h2>
            <div className="body">
              <AgentTrace steps={traceSteps} />
            </div>
          </div>
          <div className="panel" style={{ maxHeight: "42%" }}>
            <h2>Work orders</h2>
            <div className="body">
              {traceWorkOrders.length === 0 && workOrders.length === 0 ? (
                <div className="trace-empty">No work orders issued.</div>
              ) : (
                (traceWorkOrders.length ? traceWorkOrders : workOrders).map((w) => (
                  <WorkOrderCard key={w.id} wo={w} />
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
