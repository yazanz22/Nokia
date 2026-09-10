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
  onToggleTheme,
  feedLost,
  children,
}: {
  route: TabId;
  badges: Partial<Record<TabId, { count: number; tone?: "bad" | "warn" }>>;
  chips: ShellChips;
  theme: ThemeChoice;
  onToggleTheme: () => void;
  /** A snapshot arrived and then the stream stopped. Distinct from the socket
      never having connected, which the tabs show as loading rather than as a
      site where nothing is happening. */
  feedLost: boolean;
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
          {/* Decorative: the name sits beside it in text, so the mark carries no
              alternative of its own. Dimensions are stated so the header does not
              reflow when it loads. */}
          <img className="brand-mark" src="/logo.png" alt="" aria-hidden width="50" height="22" />
          {/* The company name used to be carried by the "FI" square. The mark that
              replaced it is a symbol, not a wordmark, so FILO has to be said here or
              it is not said anywhere on screen. Weighted the way the logo lockup
              weights it: FILO leads, the product name follows. */}
          <div className="brand-name">
            <span className="brand-co">FILO</span> Asset Sentinel
          </div>
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
          <ThemeToggle choice={theme} onToggle={onToggleTheme} />
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
        {/* Everything below this is the last frame that arrived, and it looks
            exactly as live as it did while it was. The relative timestamps
            freeze with it - they are computed during render, and renders stop
            when frames do - so a dashboard dead for five minutes goes on
            reporting every machine as seen seconds ago. Say so at the top
            rather than let a still picture pass for a running site. */}
        {feedLost && (
          <div className="banner is-bad" role="alert">
            Live feed lost, reconnecting. Everything below is frozen as of the last
            frame received and is no longer being updated.
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
