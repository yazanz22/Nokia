import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "./components/AppShell";
import { DashboardTab } from "./tabs/DashboardTab";
import { AssetsTab } from "./tabs/AssetsTab";
import { MaintenanceTab } from "./tabs/MaintenanceTab";
import { IncidentsTab } from "./tabs/IncidentsTab";
import { InventoryTab } from "./tabs/InventoryTab";
import { SimulationTab } from "./tabs/SimulationTab";
import { getFleetHealth, getHealth } from "./lib/api";
import { useRoute, type TabId } from "./lib/router";
import { useTheme } from "./lib/theme";
import { useLiveState } from "./lib/ws";
import { REORDER_AT } from "./lib/format";
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
  const route = useRoute();
  const { choice, cycle } = useTheme();
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  // The forecast, fetched once here and shared, so the map, the fleet table and the
  // maintenance board are all drawing the same numbers. Two components fetching it
  // separately is how the map once called a machine healthy that the predictive panel
  // had just put a day from failure.
  const [risk, setRisk] = useState<RiskRow[]>([]);
  // Whether the forecast answered at all, carried separately from what it said.
  // Collapsing both into an empty array meant a model that failed to load was
  // presented to the operator as "nothing is forecast to fail" - the pitch's
  // central claim, silently inverted, with nothing on screen to say otherwise.
  const [riskAvailable, setRiskAvailable] = useState(true);
  useEffect(() => {
    let cancelled = false;
    // Generation guard: if one poll outlives the 30s interval, a stale response
    // must not overwrite a newer one and stick until the next tick.
    let gen = 0;
    const load = () => {
      const mine = ++gen;
      return getFleetHealth()
        .then((d) => {
          if (cancelled || mine !== gen) return;
          setRiskAvailable(!!d.available);
          setRisk(d.available ? (d.assets ?? []) : []);
        })
        .catch(() => {
          if (cancelled || mine !== gen) return;
          setRiskAvailable(false);
          setRisk([]);
        });
    };
    load();
    // Not because the scores drift: the forecast is cut at a fixed instant and no live
    // telemetry reaches it, so a machine's number is the same all session. What moves
    // is which machines are scored. A dispatched or silent machine drops off the
    // roster and one back from a repair rejoins it, and the endpoint is cached
    // server-side on exactly that roster, so a poll that finds nothing changed is free.
    const timer = window.setInterval(load, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  // Selecting a machine on the map or in the table is a cross-tab selection: click a
  // row on Assets, switch to Dashboard, and the map still has it. One piece of state
  // rather than one per tab, because the alternative is two tabs disagreeing about
  // which machine you are looking at.
  const onSelectAsset = useCallback((id: string) => setSelectedAsset(id), []);

  const openIncidents = useMemo(
    () => Object.values(state.incidents).filter((i) => i.closed_at === null).length,
    [state.incidents]
  );

  // Depot lines at or below their reorder point. Computed from the websocket rather
  // than the inventory endpoint so the badge is live without that tab being open,
  // but against the same per-part reorder points the backend uses - a flat "<= 1"
  // rule counted a different set of lines from the Inventory tab's own header, so
  // the two badges for one concept visibly disagreed.
  const lowStock = useMemo(() => {
    let n = 0;
    for (const wh of Object.values(state.warehouses)) {
      for (const [part, units] of Object.entries(wh.stock)) {
        if (units <= (REORDER_AT[part] ?? 1)) n += 1;
      }
    }
    return n;
  }, [state.warehouses]);

  const badges: Partial<Record<TabId, { count: number; tone?: "bad" | "warn" }>> = {
    incidents: { count: openIncidents, tone: "bad" },
    inventory: { count: lowStock, tone: "warn" },
  };

  return (
    <AppShell
      route={route.tab}
      badges={badges}
      chips={{
        agentMode: health?.agent_mode,
        llmModel: health?.llm_model ?? null,
        mlBackend: health?.ml_backend,
        nacMode: health?.nac_mode,
        connected,
      }}
      theme={choice}
      onCycleTheme={cycle}
    >
      {route.tab === "dashboard" && (
        <DashboardTab
          state={state}
          risk={risk}
          selectedAsset={selectedAsset}
          onSelectAsset={onSelectAsset}
        />
      )}
      {route.tab === "assets" && (
        <AssetsTab
          state={state}
          risk={risk}
          selectedAsset={selectedAsset}
          onSelectAsset={onSelectAsset}
        />
      )}
      {route.tab === "maintenance" && (
        <MaintenanceTab state={state} risk={risk} riskAvailable={riskAvailable} />
      )}
      {route.tab === "incidents" && <IncidentsTab state={state} focusId={route.id} />}
      {route.tab === "inventory" && <InventoryTab state={state} />}
      {route.tab === "simulation" && (
        <SimulationTab state={state} selectedAsset={selectedAsset} />
      )}
    </AppShell>
  );
}
