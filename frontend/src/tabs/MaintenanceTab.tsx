import { useCallback, useEffect, useRef, useState } from "react";
import { Wrench } from "@phosphor-icons/react";
import { getMaintenanceSchedule, raisePredictive, raisePreventive } from "../lib/api";
import { EmptyState, ErrorState, LoadingRows } from "../components/StateBlock";
import { WorkOrderCard } from "../components/WorkOrderCard";
import type { LiveState } from "../lib/ws";
import type { BundleRow, RiskRow, ServiceRow } from "../types";
import { MAINTENANCE_LABEL, MAINTENANCE_WHY, plural, serviceDue } from "../lib/format";

interface Schedule {
  due_soon_hours: number;
  service_part: string;
  overdue: number;
  due_soon: number;
  assets: ServiceRow[];
  bundles: BundleRow[];
  forecast_available: boolean;
}

type Kind = "predictive" | "preventive" | "corrective";

/**
 * All three kinds of maintenance, named the way the industry names them.
 *
 * The distinction is what triggered the work, and it is the thing that decides
 * who plans it and what it costs. Putting them on one screen is also the only
 * way the bundling case is visible: a machine that is both due a service and
 * forecast to fail appears on two lists, and nobody reading two separate screens
 * ever notices it is one visit.
 */
export function MaintenanceTab({
  state,
  risk,
  riskAvailable,
}: {
  state: LiveState;
  risk: RiskRow[];
  riskAvailable: boolean;
}) {
  const [tab, setTab] = useState<Kind>("predictive");
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // A write triggers two reloads: this one, and the websocket frame the write
  // itself produced. Both were in flight with nothing deciding which painted, so
  // the older answer could win and stick. The generation counter settles it.
  const gen = useRef(0);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const load = useCallback(async () => {
    const mine = ++gen.current;
    setError(null);
    try {
      const d = await getMaintenanceSchedule();
      if (alive.current && mine === gen.current) setSchedule(d);
    } catch (e) {
      if (alive.current && mine === gen.current) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, state.workOrders]);

  const act = async (key: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(ok);
      // Awaited, so the buttons stay disabled until the board reflects the write.
      // Releasing on the POST alone re-enabled them over stale numbers, and the
      // next click was refused by the backend for a state the UI had shown as fine.
      await load();
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (alive.current) setBusy(null);
    }
  };

  const corrective = Object.values(state.workOrders).filter(
    (w) => w.maintenance_type === "corrective"
  );
  const scheduled = Object.values(state.workOrders).filter((w) =>
    ["preventive", "predictive"].includes(w.maintenance_type)
  );

  const atRisk = risk.filter((r) => r.at_risk);

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Maintenance</h1>
          <p className="page-sub">
            Three kinds of work, separated by what triggered them. Predictive and
            preventive are planned; corrective is what happens when neither caught it in
            time.
          </p>
        </div>
        <div className="segmented" role="group" aria-label="Maintenance type">
          {(["predictive", "preventive", "corrective"] as Kind[]).map((k) => (
            <button
              key={k}
              className={`segmented-item${tab === k ? " is-on" : ""}`}
              aria-pressed={tab === k}
              onClick={() => setTab(k)}
            >
              {MAINTENANCE_LABEL[k]}
            </button>
          ))}
        </div>
      </div>

      <p className="type-explainer">{MAINTENANCE_WHY[tab]}</p>

      {notice && (
        <div className="banner is-info" role="status">
          {notice}
        </div>
      )}
      {error && schedule && (
        <div className="banner is-bad" role="alert">
          {error}
        </div>
      )}

      {/* The overlap, shown above whichever list is open, because it is the row that
          saves a whole journey and it belongs to neither list alone. */}
      {schedule && schedule.bundles.length > 0 && tab !== "corrective" && (
        <section className="panel">
          <div className="panel-head">
            <h2>One visit, not two</h2>
            <span className="panel-note">{plural(schedule.bundles.length, "machine")}</span>
          </div>
          <div className="panel-body stack">
            <p className="text-sm text-muted" style={{ maxWidth: "72ch" }}>
              These machines are due a service and are also forecast to fail. Both jobs
              need a technician at the same machine with parts from the same depot, so
              doing them together costs one journey instead of two.
            </p>
            {schedule.bundles.map((b) => (
              <div className="bundle" key={b.asset_id}>
                <div className="bundle-main">
                  <div className="cell-primary mono">{b.asset_id}</div>
                  <div className="cell-sub">{b.label}</div>
                </div>
                <div className="bundle-facts">
                  <span className="badge is-warn">Fails in ~{b.horizon_hours ?? "?"}h</span>
                  <span className="badge">{serviceDue(b.due_in_hours)}</span>
                  <span className="text-xs text-muted mono">
                    {b.component_part} plus {b.part} at {b.depot}
                  </span>
                </div>
                <button
                  className="btn btn-primary btn-sm"
                  disabled={busy === b.asset_id || b.already_scheduled}
                  onClick={() =>
                    act(
                      b.asset_id,
                      () => raisePredictive(b.asset_id, true),
                      `Scheduled one visit for ${b.asset_id} covering the repair and the service.`
                    )
                  }
                >
                  {b.already_scheduled ? "Already scheduled" : "Schedule one visit"}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === "predictive" && (
        <section className="panel">
          <div className="panel-head">
            <h2>Forecast failures</h2>
            <span className="panel-note">{plural(atRisk.length, "machine")}</span>
          </div>
          <div className="panel-body is-flush">
            {!schedule && !error && <LoadingRows />}
            {error && !schedule && (
              <ErrorState title="Could not load the forecast" body={error} onRetry={load} />
            )}
            {schedule && !riskAvailable && (
              <EmptyState
                icon={Wrench}
                title="The forecast is unavailable"
                body="The model did not answer, so no machine has been scored. This is not an all-clear: it means nothing has been checked."
              />
            )}
            {schedule && riskAvailable && atRisk.length === 0 && (
              <EmptyState
                icon={Wrench}
                title="Nothing forecast to fail"
                body="Every in-service machine is outside the model's warning window. Machines under repair are not scored, because a forecast about a machine already being fixed is not a forecast."
              />
            )}
            {riskAvailable && atRisk.length > 0 && (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Machine</th>
                      <th scope="col" className="num">
                        Expected
                      </th>
                      <th scope="col" className="num">
                        Vibration
                      </th>
                      <th scope="col" className="num">
                        Oil particles
                      </th>
                      <th scope="col" />
                    </tr>
                  </thead>
                  <tbody>
                    {atRisk.map((r) => (
                      <tr key={r.asset_id}>
                        <td>
                          <div className="cell-primary mono">{r.asset_id}</div>
                          <div className="cell-sub">{r.label ?? ""}</div>
                        </td>
                        <td className="num mono">{r.horizon_hours ?? "?"}h</td>
                        <td className="num mono">+{r.vibration_delta.toFixed(2)}</td>
                        <td className="num mono">+{r.oil_particle_delta.toFixed(0)}</td>
                        <td className="num">
                          <button
                            className="btn btn-sm"
                            disabled={busy === r.asset_id}
                            onClick={() =>
                              act(
                                r.asset_id,
                                () => raisePredictive(r.asset_id, false),
                                `Scheduled a predictive repair for ${r.asset_id}.`
                              )
                            }
                          >
                            Schedule
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      {tab === "preventive" && (
        <section className="panel">
          <div className="panel-head">
            <h2>Service board</h2>
            {schedule && (
              <span className="panel-note">
                {schedule.overdue} overdue, {schedule.due_soon} due soon
              </span>
            )}
          </div>
          <div className="panel-body is-flush">
            {!schedule && !error && <LoadingRows />}
            {error && <ErrorState title="Could not load the schedule" body={error} onRetry={load} />}
            {schedule && schedule.assets.length === 0 && (
              <EmptyState
                icon={Wrench}
                title="Nothing due"
                body={`No machine is within ${schedule.due_soon_hours} hours of its service interval.`}
              />
            )}
            {schedule && schedule.assets.length > 0 && (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Machine</th>
                      <th scope="col" className="num">
                        Engine hours
                      </th>
                      <th scope="col" className="num">
                        Since service
                      </th>
                      <th scope="col" className="num">
                        Due
                      </th>
                      <th scope="col" />
                    </tr>
                  </thead>
                  <tbody>
                    {schedule.assets.map((s) => (
                      <tr key={s.asset_id}>
                        <td>
                          <div className="cell-primary mono">{s.asset_id}</div>
                          <div className="cell-sub">{s.label}</div>
                        </td>
                        <td className="num mono">{s.engine_hours.toFixed(0)}</td>
                        <td className="num mono">{s.hours_since_service.toFixed(0)}</td>
                        <td className={`num mono${s.state === "overdue" ? " is-overdue" : ""}`}>
                          {serviceDue(s.due_in_hours)}
                        </td>
                        <td className="num">
                          <button
                            className="btn btn-sm"
                            disabled={busy === s.asset_id}
                            onClick={() =>
                              act(
                                s.asset_id,
                                () => raisePreventive(s.asset_id),
                                `Scheduled the ${s.service_interval_hours.toFixed(0)}-hour service for ${s.asset_id}.`
                              )
                            }
                          >
                            Schedule
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      {tab === "corrective" && (
        <section className="panel">
          <div className="panel-head">
            <h2>Repairs after failure</h2>
            <span className="panel-note">{corrective.length}</span>
          </div>
          <div className="panel-body stack">
            {corrective.length === 0 ? (
              <EmptyState
                icon={Wrench}
                title="No corrective work"
                body="Nothing has broken. Corrective jobs are raised by the agent when it confirms a genuine fault, never by hand."
              />
            ) : (
              corrective.map((w) => <WorkOrderCard key={w.id} wo={w} />)
            )}
          </div>
        </section>
      )}

      {tab !== "corrective" && scheduled.length > 0 && (
        <section className="panel">
          <div className="panel-head">
            <h2>Scheduled work</h2>
            <span className="panel-note">{scheduled.length}</span>
          </div>
          <div className="panel-body stack">
            {scheduled.map((w) => (
              <WorkOrderCard key={w.id} wo={w} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
