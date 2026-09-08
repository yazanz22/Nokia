import { useMemo, useState } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import type { LiveState } from "../lib/ws";
import type { Asset, RiskRow } from "../types";
import { EmptyState, LoadingRows } from "../components/StateBlock";
import {
  ASSET_STATE_LABEL,
  GROUP_LABEL,
  STATE_GROUP,
  ago,
  serviceDue,
  siteLabel,
} from "../lib/format";

type SortKey = "id" | "state" | "site" | "hours" | "service" | "seen";

const GROUP_TONE: Record<string, string> = {
  healthy: "is-ok",
  attention: "is-bad",
  nocoverage: "is-info",
  handled: "is-accent",
};

/**
 * The fleet as a list.
 *
 * A map answers "where", and it is the wrong tool for "which of these is worst"
 * or "show me everything at Trojena". This is the surface for working through
 * thirty machines in order, which is how somebody responsible for them actually
 * reads a fleet.
 */
export function AssetsTab({
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
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("id");
  const [asc, setAsc] = useState(true);

  const riskById = useMemo(() => {
    const m: Record<string, RiskRow> = {};
    for (const r of risk) if (r.at_risk) m[r.asset_id] = r;
    return m;
  }, [risk]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = Object.values(state.assets).filter(
      (a) =>
        !q ||
        a.id.toLowerCase().includes(q) ||
        a.label.toLowerCase().includes(q) ||
        a.site.toLowerCase().includes(q)
    );
    const dir = asc ? 1 : -1;
    const key = (a: Asset) => {
      switch (sort) {
        case "state":
          return STATE_GROUP[a.state];
        case "site":
          return a.site;
        case "hours":
          return a.engine_hours;
        case "service":
          return a.service_interval_hours - a.hours_since_service;
        case "seen":
          return a.last_seen;
        default:
          return a.id;
      }
    };
    return [...list].sort((x, y) => {
      const kx = key(x);
      const ky = key(y);
      if (kx === ky) return x.id.localeCompare(y.id);
      return (kx > ky ? 1 : -1) * dir;
    });
  }, [state.assets, query, sort, asc]);

  const fleetSize = Object.keys(state.assets).length;
  const selected = selectedAsset ? state.assets[selectedAsset] : null;
  const latest = selectedAsset ? state.latestTelemetry[selectedAsset] : null;
  const selectedRisk = selectedAsset ? riskById[selectedAsset] : null;

  // The click handler moves onto a button inside the header rather than the <th>,
  // so sorting is reachable by Tab. aria-sort stays on the cell, where it belongs.
  const th = (k: SortKey, label: string, numeric = false) => (
    <th
      className={`sortable${numeric ? " num" : ""}`}
      aria-sort={sort === k ? (asc ? "ascending" : "descending") : "none"}
      scope="col"
    >
      <button
        type="button"
        className="th-sort"
        onClick={() => {
          if (sort === k) setAsc((v) => !v);
          else {
            setSort(k);
            setAsc(true);
          }
        }}
      >
        {label}
        {sort === k && <span aria-hidden>{asc ? " ↑" : " ↓"}</span>}
      </button>
    </th>
  );

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Assets</h1>
          <p className="page-sub">
            Every machine on the site, its current state, and where it stands against its
            service interval.
          </p>
        </div>
        <div className="field" style={{ minWidth: 240 }}>
          <label className="field-label" htmlFor="asset-search">
            Search
          </label>
          <div className="input-icon">
            <MagnifyingGlass size={14} aria-hidden />
            <input
              id="asset-search"
              className="input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Machine, site or id"
            />
          </div>
        </div>
      </div>

      <div className="grid-main">
        <section className="panel">
          <div className="panel-head">
            <h2>Fleet</h2>
            <span className="panel-note">
              {rows.length} of {fleetSize}
            </span>
          </div>
          <div className="panel-body is-flush">
            {fleetSize === 0 ? (
              <LoadingRows rows={8} />
            ) : rows.length === 0 ? (
              <EmptyState
                icon={MagnifyingGlass}
                title="No machine matches that"
                body="Try an id like EQ-0180, a machine type, or a site name."
              />
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      {th("id", "Machine")}
                      {th("state", "State")}
                      {th("site", "Site")}
                      {th("hours", "Engine hours", true)}
                      {th("service", "Next service", true)}
                      {th("seen", "Last seen", true)}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((a) => {
                      const group = STATE_GROUP[a.state];
                      const due = a.service_interval_hours - a.hours_since_service;
                      const r = riskById[a.id];
                      return (
                        <tr
                          key={a.id}
                          className={`is-clickable${a.id === selectedAsset ? " is-selected" : ""}`}
                          onClick={() => onSelectAsset(a.id)}
                        >
                          <td>
                            {/* The row keeps its onClick for the mouse; this is what
                                makes the machine selectable by keyboard. */}
                            <button
                              type="button"
                              className="cell-open cell-primary mono"
                              aria-current={a.id === selectedAsset ? "true" : undefined}
                              onClick={(e) => {
                                e.stopPropagation();
                                onSelectAsset(a.id);
                              }}
                            >
                              {a.id}
                            </button>
                            <div className="cell-sub">{a.label}</div>
                          </td>
                          <td>
                            <span className={`badge ${GROUP_TONE[group]}`}>
                              {ASSET_STATE_LABEL[a.state]}
                            </span>
                            {r?.horizon_hours != null && (
                              <span className="badge is-warn">Fails in ~{r.horizon_hours}h</span>
                            )}
                          </td>
                          <td className="cell-sub">{siteLabel(a.site)}</td>
                          <td className="num mono">{a.engine_hours.toFixed(0)}</td>
                          <td className={`num mono${due <= 0 ? " is-overdue" : ""}`}>
                            {serviceDue(due)}
                          </td>
                          <td className="num cell-sub">{ago(a.last_seen)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Detail</h2>
            {selected && <span className="panel-note mono">{selected.id}</span>}
          </div>
          <div className="panel-body">
            {!selected ? (
              <EmptyState
                title="No machine selected"
                body="Pick a row to see its telemetry, its service position, and what the forecast expects of it."
              />
            ) : (
              <div className="stack">
                <div>
                  <div className="text-sm cell-primary">{selected.label}</div>
                  <div className="text-xs text-muted">{siteLabel(selected.site)}</div>
                </div>

                <div className="row">
                  <span className={`badge ${GROUP_TONE[STATE_GROUP[selected.state]]}`}>
                    {GROUP_LABEL[STATE_GROUP[selected.state]]}
                  </span>
                  {selectedRisk?.horizon_hours != null && (
                    <span className="badge is-warn">Fails in ~{selectedRisk.horizon_hours}h</span>
                  )}
                  {selected.offsite && <span className="badge is-info">Outside the perimeter</span>}
                </div>

                {/* Both badges can be true at once, and that is the argument for the
                    model: a machine streaming perfectly can still be a day from a
                    bearing failure. */}
                {selectedRisk && (
                  <div className="banner is-warn">
                    <div>
                      Healthy right now and still expected to fail. Vibration is up{" "}
                      <b>{selectedRisk.vibration_delta.toFixed(2)}</b> and oil particles up{" "}
                      <b>{selectedRisk.oil_particle_delta.toFixed(0)}</b>, which move days
                      ahead. Engine temperature, the channel a threshold alarm watches, has
                      not moved yet.
                    </div>
                  </div>
                )}

                <dl className="dl">
                  <dt>Engine hours</dt>
                  <dd className="mono">{selected.engine_hours.toFixed(0)} h</dd>
                  <dt>Since service</dt>
                  <dd className="mono">{selected.hours_since_service.toFixed(0)} h</dd>
                  <dt>Interval</dt>
                  <dd className="mono">{selected.service_interval_hours.toFixed(0)} h</dd>
                  <dt>Next service</dt>
                  <dd
                    className={`mono${
                      selected.service_interval_hours - selected.hours_since_service <= 0
                        ? " is-overdue"
                        : ""
                    }`}
                  >
                    {serviceDue(selected.service_interval_hours - selected.hours_since_service)}
                  </dd>
                  <dt>Last seen</dt>
                  <dd>{ago(selected.last_seen)}</dd>
                </dl>

                {latest && (
                  <>
                    <div className="panel-head is-inline">
                      <h3>Live telemetry</h3>
                    </div>
                    <dl className="dl">
                      <dt>Engine temp</dt>
                      <dd className="mono">{latest.engine_temp_c.toFixed(1)} °C</dd>
                      <dt>Signal</dt>
                      <dd className="mono">{latest.signal_strength_dbm.toFixed(0)} dBm</dd>
                      <dt>Neighbour fails</dt>
                      <dd className="mono">{latest.neighbor_fail_count}</dd>
                      <dt>Telemetry age</dt>
                      <dd className="mono">{latest.telemetry_age_sec.toFixed(0)} s</dd>
                    </dl>
                  </>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
