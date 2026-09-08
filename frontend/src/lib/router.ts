import { useEffect, useState } from "react";

export type TabId =
  | "dashboard"
  | "assets"
  | "maintenance"
  | "incidents"
  | "inventory"
  | "simulation";

export const TABS: TabId[] = [
  "dashboard",
  "assets",
  "maintenance",
  "incidents",
  "inventory",
  "simulation",
];

export interface Route {
  tab: TabId;
  /** Optional focused record, e.g. an incident id on the incidents tab. */
  id: string | null;
}

function parse(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  const [tab, id] = raw.split("/");
  const known = (TABS as string[]).includes(tab) ? (tab as TabId) : "dashboard";
  return { tab: known, id: id ? decodeURIComponent(id) : null };
}

export function href(tab: TabId, id?: string) {
  return id ? `#/${tab}/${encodeURIComponent(id)}` : `#/${tab}`;
}

/**
 * Go to a route.
 *
 * `replace` exists because two different things call this. A user clicking a row
 * is navigation and should be undoable with Back. A component reconciling the URL
 * with a selection it derived itself is not: pushing there meant Back landed on
 * the bare tab, the component immediately re-derived the same selection and
 * pushed it again, and the Back button appeared frozen while the history stack
 * grew on every press.
 */
export function navigate(tab: TabId, id?: string, replace = false) {
  const next = href(tab, id);
  if (location.hash === next) return;
  if (replace) location.replace(next);
  else location.hash = next;
}

/**
 * Hash routing, hand-rolled rather than pulled in.
 *
 * The app has six tabs and one optional record id, which `hashchange` answers
 * completely. A router library would add a dependency and a build surface for a
 * problem this size. Hash rather than history so the single-container deploy
 * needs no server-side rewrite rule: FastAPI serves one index.html and every
 * route is resolved in the browser.
 */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parse(location.hash));
    // Normalise rather than only filling an empty hash. `parse` falls back to the
    // dashboard for anything it does not recognise, so without this a typo'd or
    // stale link rendered the dashboard while the address bar still claimed to be
    // somewhere else, and copying that URL propagated the lie.
    const parsed = parse(location.hash);
    const canonical = href(parsed.tab, parsed.id ?? undefined);
    if (location.hash !== canonical) location.replace(canonical);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}
