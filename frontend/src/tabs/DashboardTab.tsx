import { useCallback, useMemo, useState } from "react";
import { FleetMap } from "../components/FleetMap";
import { KpiBar } from "../components/KpiBar";
import { AgentStatus } from "../components/AgentTrace";
import { WorkOrderCard } from "../components/WorkOrderCard";
import { EmptyState, LoadingRows } from "../components/StateBlock";
import type { LiveState } from "../lib/ws";
import type { RiskRow } from "../types";
import { href } from "../lib/router";
import { ago, km, plural } from "../lib/format";
import { closeNoFaultFound, completeWorkOrder, deleteWorkOrder } from "../lib/api";

/**
 * The monitoring surface: what is happening on the site right now.
 *
 * Everything here answers "is anything wrong, and is it being handled". Detail
 * lives one tab away by design. The agent's reasoning in particular is reduced
 * to what it is doing and what it concluded, because a dispatcher scanning a
 * site does not read a transcript, and the transcript pushed the map and the
 * work orders off the screen when it was here in full.
 */
export function DashboardTab({
  state,
  risk,
  selectedAsset,
  onSelectAsset,
}: {
  state: LiveState;
  risk: RiskRow[];
  selectedAsset: string | null;
  onSelectAsset: (id: string) => void;
}) {
  // Closing a job is the one place the dashboard writes rather than reads, so it
  // owns the in-flight and error state for it. The websocket delivers the result,
  // which is why nothing here reaches back for the updated work order.
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const run = useCallback(
    (id: string, fn: (id: string) => Promise<unknown>) => {
      setBusy(id);
      setActionError(null);
      fn(id)
        .catch((e) => setActionError(e instanceof Error ? e.message : String(e)))
        .finally(() => setBusy(null));
    },
    []
  );

  const assets = useMemo(() => Object.values(state.assets), [state.assets]);
  const technicians = useMemo(() => Object.values(state.technicians), [state.technicians]);
  const warehouses = useMemo(() => Object.values(state.warehouses), [state.warehouses]);
  const workOrders = useMemo(() => Object.values(state.workOrders), [state.workOrders]);
  const incidents = useMemo(() => Object.values(state.incidents), [state.incidents]);

  const riskById = useMemo(() => {
    const m: Record<string, RiskRow> = {};
    for (const r of risk) if (r.at_risk) m[r.asset_id] = r;
    return m;
  }, [risk]);

  // The live one if there is one, else the most recent. The dashboard follows the
  // site rather than a selection: something going dark is the thing you want on
  // screen, and it is why this panel does not wait to be clicked.
  const focused = useMemo(() => {
    // Newest first in BOTH branches. incidents is in insertion order, so a
    // bare .find() returned the oldest still-open one while the closed
    // fallback below returned the newest: inject a second scenario while the
    // first is still triaging and the panel narrates the one nobody is
    // pointing at, then jumps mid-sentence when the older one closes.
    const byNewest = [...incidents].sort((a, b) => b.opened_at.localeCompare(a.opened_at));
    return byNewest.find((i) => i.closed_at === null) ?? byNewest[0];
  }, [incidents]);

  const openWorkOrders = workOrders
    .filter((w) => w.status !== "completed")
    .sort((a, b) => b.created_at.localeCompare(a.created_at));

  const alerts = useMemo(
    () => Object.values(state.geofenceAlerts).sort((a, b) => b.at.localeCompare(a.at)),
    [state.geofenceAlerts]
  );

  return (
    <main className="page">
      {/* Every other tab opens with a visible h1. The dashboard's title is the
          product itself, so it is named for assistive tech rather than repeated
          on screen above a KPI row that already says what this is. */}
      <h1 className="sr-only">Dashboard</h1>
      <KpiBar kpis={state.kpis} />

      <div className="grid-main">
        <section className="panel">
          <div className="panel-head">
            <h2>Site map</h2>
            <span className="panel-note">
              {plural(assets.length, "machine")}, {plural(technicians.length, "technician")},{" "}
              {plural(warehouses.length, "depot")}
            </span>
          </div>
          <FleetMap
            assets={assets}
            technicians={technicians}
            warehouses={warehouses}
            workOrders={workOrders}
            deadZones={state.deadZones}
            riskById={riskById}
            selectedId={selectedAsset}
            onSelect={onSelectAsset}
          />
        </section>

        <div className="stack" style={{ minHeight: 0 }}>
          <section className="panel">
            <div className="panel-head">
              <h2>Agent</h2>
              {focused && (
                <a className="panel-note" href={href("incidents", focused.id)}>
                  All incidents
                </a>
              )}
            </div>
            {/* The agent's verdict changes with nobody watching. Announcing it is
                the only way a screen-reader user learns the site state moved. */}
            <div className="panel-body" aria-live="polite" aria-atomic="true">
              <AgentStatus
                incident={focused}
                steps={focused ? (state.trace[focused.id] ?? []) : []}
                ready={state.ready}
              />
            </div>
          </section>

          {alerts.length > 0 && (
            <section className="panel">
              <div className="panel-head">
                <h2>Perimeter</h2>
                <span className="panel-note">Caught on the way out, not after going dark</span>
              </div>
              <div className="panel-body stack">
                {alerts.slice(0, 3).map((a) => (
                  <div className="banner is-info" key={a.id}>
                    <div>
                      <b>{a.asset_label || a.asset_id}</b> crossed the site perimeter
                      {a.distance_km >= 0.1 ? `, now ${km(a.distance_km)} beyond it` : ""}. Still
                      healthy, still reporting.
                      <div className="text-xs text-muted" style={{ marginTop: "var(--s-1)" }}>
                        {ago(a.at)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="panel" style={{ flex: "1 1 auto" }}>
            <div className="panel-head">
              <h2>Open work orders</h2>
              <span className="panel-note">{openWorkOrders.length}</span>
            </div>
            <div className="panel-body stack">
              {actionError && (
                <div className="banner is-bad" role="alert">
                  {actionError}
                </div>
              )}
              {!state.ready ? (
                <LoadingRows rows={3} />
              ) : openWorkOrders.length === 0 ? (
                <EmptyState
                  title="Nobody is out"
                  body="A work order is raised only once the network has been ruled out as the cause. An empty list here is the saving, not a gap in the record."
                />
              ) : (
                openWorkOrders.map((w) => (
                  <WorkOrderCard
                    key={w.id}
                    wo={w}
                    busy={busy === w.id}
                    onComplete={(id) => run(id, completeWorkOrder)}
                    onNoFault={(id) => run(id, closeNoFaultFound)}
                    onDelete={(id) => run(id, deleteWorkOrder)}
                  />
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
