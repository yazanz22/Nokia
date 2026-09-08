import {
  Broadcast,
  Cube,
  Gauge,
  type Icon,
  Truck,
  Warning,
  Wrench,
} from "@phosphor-icons/react";
import { useEffect, useRef } from "react";
import { href, type TabId, TABS } from "../lib/router";
import type { ThemeChoice } from "../lib/theme";
import { ThemeToggle } from "./ThemeToggle";

const TAB_META: Record<TabId, { label: string; icon: Icon }> = {
  dashboard: { label: "Dashboard", icon: Gauge },
  assets: { label: "Assets", icon: Truck },
  maintenance: { label: "Maintenance", icon: Wrench },
  incidents: { label: "Incidents", icon: Warning },
  inventory: { label: "Inventory", icon: Cube },
  simulation: { label: "Simulation", icon: Broadcast },
};

export interface ShellChips {
  agentMode?: string;
  llmModel?: string | null;
  mlBackend?: string;
  nacMode?: string;
  connected: boolean;
}

/**
 * Top bar and tab navigation.
 *
 * Badges carry real counts (open incidents, depots below their reorder point)
 * so that work arriving on a tab you are not looking at is visible without
 * stealing the tab you are on. That is deliberate: an operator mid-way through
 * reading an asset should not be yanked to the dashboard because a machine went
 * quiet. The badge says "there is something here", and they choose when.
 */
export function AppShell({
  route,
  badges,
  chips,
  theme,
  onCycleTheme,
  children,
}: {
  route: TabId;
  badges: Partial<Record<TabId, { count: number; tone?: "bad" | "warn" }>>;
  chips: ShellChips;
  theme: ThemeChoice;
  onCycleTheme: () => void;
  children: React.ReactNode;
}) {
  // Switching tabs swaps the entire page while focus stays on the nav link, so a
  // keyboard user's next Tab continued through the remaining nav items rather than
  // into the content that just appeared. Moving focus to the content region on a
  // route change is what makes the six tabs usable without a mouse. Skipped on
  // first paint, where nothing has been navigated yet.
  const contentRef = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    contentRef.current?.focus();
  }, [route]);

  return (
    <div className="app">
      {/* Eleven tab stops sit between the top of the document and the content. */}
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden>
            FI
          </div>
          <div className="brand-name">Asset Sentinel</div>
        </div>

        <div className="topbar-spacer" />

        <div className="topbar-meta">
          {chips.agentMode && (
            <span className="chip" title={chips.llmModel ?? undefined}>
              Agent <b>{chips.agentMode === "llm" ? "LLM" : "Rule"}</b>
            </span>
          )}
          {chips.mlBackend && (
            <span className="chip">
              Models <b>{chips.mlBackend === "trained" ? "Trained" : chips.mlBackend}</b>
            </span>
          )}
          {chips.nacMode && (
            <span className="chip">
              CAMARA <b>{chips.nacMode === "live" ? "Live" : "Mock"}</b>
            </span>
          )}
          {/* A real status, not decoration: it changes without user action and it
              is how an operator knows the view is still live. */}
          <span className={`chip${chips.connected ? "" : " is-off"}`} role="status">
            <span className="chip-live-dot" aria-hidden />
            {chips.connected ? "Streaming" : "Reconnecting"}
          </span>
          <ThemeToggle choice={theme} onCycle={onCycleTheme} />
        </div>
      </header>

      <nav className="tabbar" aria-label="Sections">
        {TABS.map((tab) => {
          const { label, icon: TabIcon } = TAB_META[tab];
          const badge = badges[tab];
          const current = route === tab;
          return (
            <a
              key={tab}
              className="tab"
              href={href(tab)}
              aria-current={current ? "page" : undefined}
            >
              <TabIcon size={15} weight={current ? "fill" : "regular"} aria-hidden />
              {label}
              {badge && badge.count > 0 && (
                <span className={`tab-badge${badge.tone === "warn" ? " is-warn" : ""}`}>
                  {badge.count}
                </span>
              )}
            </a>
          );
        })}
      </nav>

      <div className="app-content" id="content" ref={contentRef} tabIndex={-1}>
        {children}
      </div>
    </div>
  );
}
