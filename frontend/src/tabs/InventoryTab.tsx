import { useCallback, useEffect, useRef, useState } from "react";
import { Cube, Minus, Plus } from "@phosphor-icons/react";
import { adjustStock, getInventory } from "../lib/api";
import { EmptyState, ErrorState, LoadingRows } from "../components/StateBlock";
import { plural } from "../lib/format";
import type { DepotStock, StockRow } from "../types";
import type { LiveState } from "../lib/ws";

interface Inventory {
  warehouses: DepotStock[];
  fleet_totals: StockRow[];
  van_stock: string[];
}

/**
 * Depot stock, and the controls to move it.
 *
 * Adjustments are deltas rather than absolute values on purpose. Stock moves by
 * events, and a "set to N" control loses the race against a dispatch that claims
 * a unit while somebody is typing: the write-back would put it straight back on
 * the shelf and two jobs would leave with one alternator. A delta commutes with
 * a concurrent claim, so it cannot.
 */
export function InventoryTab({ state }: { state: LiveState }) {
  const [inv, setInv] = useState<Inventory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Same two-in-flight problem as the maintenance board: the explicit reload and
  // the websocket frame the write produced raced, and the loser could paint last.
  const gen = useRef(0);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const load = useCallback(async () => {
    const mine = ++gen.current;
    setError(null);
    try {
      const d = await getInventory();
      if (alive.current && mine === gen.current) setInv(d);
    } catch (e) {
      if (alive.current && mine === gen.current) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }, []);

  // Reload when the websocket says stock moved, so a dispatch that takes the last
  // alternator is visible here without a refresh.
  useEffect(() => {
    load();
  }, [load, state.warehouses]);

  const adjust = async (warehouseId: string, part: string, delta: number) => {
    const key = `${warehouseId}:${part}`;
    setBusy(key);
    setError(null);
    try {
      await adjustStock(warehouseId, part, delta);
      // Awaited: releasing on the POST alone re-enabled the buttons while the table
      // still showed pre-adjustment numbers, so a second click passed a guard
      // evaluated against stale stock and came back a 409.
      await load();
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (alive.current) setBusy(null);
    }
  };

  const lowTotal = inv?.warehouses.reduce((s, w) => s + w.low_count, 0) ?? 0;

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Inventory</h1>
          <p className="page-sub">
            What each depot holds. A dispatch claims its parts before anyone drives
            anywhere, so these numbers are what the routing is deciding against.
          </p>
        </div>
        {lowTotal > 0 && (
          <span className="badge is-warn">
            {plural(lowTotal, "line")} at or below reorder point
          </span>
        )}
      </div>

      {/* Only once the table exists. On a first-load failure the ErrorState below
          is the single surface, rather than the same sentence twice. */}
      {error && inv && (
        <div className="banner is-bad" role="alert">
          {error}
        </div>
      )}

      {!inv && !error && (
        <section className="panel">
          <div className="panel-body">
            <LoadingRows rows={6} />
          </div>
        </section>
      )}

      {error && !inv && (
        <section className="panel">
          <div className="panel-body">
            <ErrorState title="Could not load stock" body={error} onRetry={load} />
          </div>
        </section>
      )}

      {inv && (
        <>
          <div className="grid-2">
            {inv.warehouses.map((wh) => (
              <section className="panel" key={wh.id}>
                <div className="panel-head">
                  <h2>{wh.name}</h2>
                  <span className="panel-note">
                    {wh.low_count > 0
                      ? `${wh.low_count} at reorder point`
                      : "Nothing at reorder point"}
                  </span>
                </div>
                <div className="panel-body is-flush">
                  {wh.parts.length === 0 ? (
                    <EmptyState
                      icon={Cube}
                      title="This depot holds no stock"
                      body="Nothing here can be collected, so no dispatch will be routed through it. Stock arrives with a delivery, or comes back from a job closed as no fault found."
                    />
                  ) : (
                    <div className="table-wrap">
                      <table className="data">
                        <thead>
                          <tr>
                            <th scope="col">Part</th>
                            <th scope="col" className="num">
                              On hand
                            </th>
                            <th scope="col" className="num">
                              Reorder at
                            </th>
                            <th scope="col" className="num">
                              Adjust
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {wh.parts.map((p) => {
                            const key = `${wh.id}:${p.part}`;
                            return (
                              <tr key={p.part}>
                                <td>
                                  <div className="cell-primary mono">{p.part}</div>
                                  <div className="cell-sub">{p.label}</div>
                                </td>
                                <td className="num mono">
                                  {p.units}
                                  {p.out && <span className="badge is-bad">Out</span>}
                                  {!p.out && p.low && <span className="badge is-warn">Low</span>}
                                </td>
                                <td className="num mono text-muted">{p.reorder_at}</td>
                                <td className="num">
                                  <div className="row" style={{ justifyContent: "flex-end" }}>
                                    <button
                                      className="btn btn-sm btn-icon"
                                      disabled={busy === key || p.units <= 0}
                                      onClick={() => adjust(wh.id, p.part, -1)}
                                      aria-label={`Write off one ${p.part} at ${wh.name}`}
                                      title="Write one off"
                                    >
                                      <Minus size={13} aria-hidden />
                                    </button>
                                    <button
                                      className="btn btn-sm btn-icon"
                                      disabled={busy === key}
                                      onClick={() => adjust(wh.id, p.part, 1)}
                                      aria-label={`Receipt one ${p.part} at ${wh.name}`}
                                      title="Receipt one"
                                    >
                                      <Plus size={13} aria-hidden />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </section>
            ))}
          </div>

          <section className="panel">
            <div className="panel-head">
              <h2>Across the site</h2>
              <span className="panel-note">
                Held anywhere is not the same as held where it is needed
              </span>
            </div>
            <div className="panel-body is-flush">
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Part</th>
                      <th scope="col" className="num">
                        Total on site
                      </th>
                      <th scope="col">Held at</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inv.fleet_totals.map((p) => {
                      const at = inv.warehouses
                        .filter((w) => (w.parts.find((x) => x.part === p.part)?.units ?? 0) > 0)
                        .map((w) => w.name);
                      return (
                        <tr key={p.part}>
                          <td>
                            <div className="cell-primary mono">{p.part}</div>
                            <div className="cell-sub">{p.label}</div>
                          </td>
                          <td className="num mono">{p.units}</td>
                          <td className="cell-sub">
                            {at.length === 0 ? "Nowhere on site" : at.join(", ")}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Carried in the van</h2>
            </div>
            <div className="panel-body">
              <p className="text-sm text-muted" style={{ maxWidth: "72ch" }}>
                These ride with every technician and never appear on a shelf, which is why
                a sensor fault dispatches direct with no depot stop. The four failing
                components are pallet items and cannot: a 40 litre hydraulic pump is a
                forklift job.
              </p>
              <div className="row" style={{ marginTop: "var(--s-3)", flexWrap: "wrap" }}>
                {inv.van_stock.map((p) => (
                  <span className="badge is-ok mono" key={p}>
                    {p}
                  </span>
                ))}
              </div>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
