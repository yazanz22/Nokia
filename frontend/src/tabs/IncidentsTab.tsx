import { useEffect, useMemo, useState } from "react";
import { ShieldCheck } from "@phosphor-icons/react";
import { AgentTrace } from "../components/AgentTrace";
import { WorkOrderCard } from "../components/WorkOrderCard";
import { EmptyState } from "../components/StateBlock";
import type { LiveState } from "../lib/ws";
import type { IncidentStatus } from "../types";
import { href, navigate } from "../lib/router";
import { ago, clockTime } from "../lib/format";

const STATUS_META: Record<IncidentStatus, { label: string; tone: string }> = {
  open: { label: "Open", tone: "is-bad" },
  investigating: { label: "Investigating", tone: "is-warn" },
  network_blindspot: { label: "Coverage gap", tone: "is-info" },
  no_fault: { label: "Nothing wrong", tone: "is-ok" },
  roaming_blocked: { label: "Roamed abroad", tone: "is-info" },
  sensor_confirmed: { label: "Sensor fault", tone: "is-warn" },
  hardware_confirmed: { label: "Hardware fault", tone: "is-bad" },
  awaiting_crew: { label: "Waiting for crew", tone: "is-warn" },
  awaiting_part: { label: "Waiting for a part", tone: "is-warn" },
  closed: { label: "Closed", tone: "" },
};

/** Outcomes where the answer was "send nobody". The product, in one filter. */
const NO_DISPATCH: IncidentStatus[] = ["network_blindspot", "roaming_blocked", "no_fault"];

/**
 * The incident record, and the full agent transcript.
 *
 * This is the reading surface. The dashboard says what is happening; this says
 * why, at whatever length the reasoning actually took. Splitting them is what
 * let the dashboard get quiet without losing the transcript that makes the
 * system auditable.
 */
export function IncidentsTab({ state, focusId }: { state: LiveState; focusId: string | null }) {
  const incidents = useMemo(
    () =>
      Object.values(state.incidents).sort((a, b) => b.opened_at.localeCompare(a.opened_at)),
    [state.incidents]
  );

  const [filter, setFilter] = useState<"all" | "nodispatch" | "dispatched" | "open">("all");

  const shown = useMemo(() => {
    switch (filter) {
      case "open":
        return incidents.filter((i) => i.closed_at === null);
      case "nodispatch":
        return incidents.filter((i) => NO_DISPATCH.includes(i.status));
      case "dispatched":
        return incidents.filter((i) =>
          ["sensor_confirmed", "hardware_confirmed"].includes(i.status)
        );
      default:
        return incidents;
    }
  }, [incidents, filter]);

  // Follow the URL when it names an incident, otherwise the newest of whatever the
  // filter is showing.
  //
  // The URL only wins while its incident is actually in the filtered list. Without
  // that check, filtering to "Dispatched" left the reading pane showing the full
  // reasoning for a coverage-gap incident while the list beside it said there was
  // nothing to see: the two halves of the screen disagreed about what was selected.
  const urlPick =
    focusId && state.incidents[focusId] && shown.some((i) => i.id === focusId)
      ? focusId
      : null;
  const selectedId = urlPick ?? shown[0]?.id ?? null;
  const selected = selectedId ? state.incidents[selectedId] : undefined;
  const steps = selectedId ? (state.trace[selectedId] ?? []) : [];
  const relatedWork = useMemo(
    () => Object.values(state.workOrders).filter((w) => w.incident_id === selectedId),
    [state.workOrders, selectedId]
  );

  // Keep the address bar honest, so a refresh or a shared link reopens the same one.
  useEffect(() => {
    // Replace, not push. Pushing a selection the component derived itself meant
    // Back landed on the bare tab, this effect immediately re-derived the same
    // selection and pushed it again, so the Back button appeared frozen and the
    // history stack grew on every press.
    if (selectedId && selectedId !== focusId) navigate("incidents", selectedId, true);
  }, [selectedId, focusId]);

  const avoided = incidents.filter((i) => NO_DISPATCH.includes(i.status)).length;

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Incidents</h1>
          <p className="page-sub">
            Every machine that went quiet, what the network said about it, and what the
            agent decided.{" "}
            {avoided > 0 && `${avoided} of those below resolved without sending anyone.`}
          </p>
        </div>
        <div className="segmented" role="group" aria-label="Filter incidents">
          {(
            [
              ["all", "All"],
              ["open", "Open"],
              ["nodispatch", "No dispatch"],
              ["dispatched", "Dispatched"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              className={`segmented-item${filter === k ? " is-on" : ""}`}
              aria-pressed={filter === k}
              onClick={() => setFilter(k)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid-main">
        <section className="panel">
          <div className="panel-head">
            <h2>Record</h2>
            <span className="panel-note">{shown.length}</span>
          </div>
          <div className="panel-body is-flush">
            {shown.length === 0 ? (
              <EmptyState
                icon={ShieldCheck}
                title={filter === "all" ? "No incidents" : "Nothing under this filter"}
                body={
                  filter === "all"
                    ? "Every machine is reporting. Incidents open on their own when a heartbeat stops."
                    : "Try another filter, or clear it to see the whole record."
                }
              />
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Incident</th>
                      <th scope="col">Machine</th>
                      <th scope="col">Outcome</th>
                      <th scope="col" className="num">
                        Opened
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((i) => {
                      const meta = STATUS_META[i.status] ?? { label: i.status, tone: "" };
                      return (
                        <tr
                          key={i.id}
                          className={`is-clickable${i.id === selectedId ? " is-selected" : ""}`}
                          onClick={() => navigate("incidents", i.id)}
                        >
                          <td className="mono cell-primary">
                            {/* An anchor, because this is navigation: it is
                                keyboard-reachable and middle-clickable. */}
                            <a
                              className="cell-open"
                              href={href("incidents", i.id)}
                              aria-current={i.id === selectedId ? "true" : undefined}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {i.id}
                            </a>
                          </td>
                          <td className="mono">{i.asset_id}</td>
                          <td>
                            <span className={`badge ${meta.tone}`}>{meta.label}</span>
                          </td>
                          <td className="num cell-sub">{clockTime(i.opened_at)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        <div className="stack" style={{ minHeight: 0 }}>
          <section className="panel" style={{ flex: "1 1 auto" }}>
            <div className="panel-head">
              <h2>Agent reasoning</h2>
              {selected && <span className="panel-note mono">{selected.id}</span>}
            </div>
            <div className="panel-body">
              {!selected ? (
                <EmptyState
                  title="No incident selected"
                  body="Pick one from the record to read how the agent reached its verdict, step by step."
                />
              ) : (
                <>
                  {selected.resolution && (
                    <div className="banner" style={{ marginBottom: "var(--s-4)" }}>
                      <div>{selected.resolution}</div>
                    </div>
                  )}
                  <AgentTrace steps={steps} active={selected.closed_at === null} />
                </>
              )}
            </div>
          </section>

          {relatedWork.length > 0 && (
            <section className="panel">
              <div className="panel-head">
                <h2>Work raised</h2>
              </div>
              <div className="panel-body stack">
                {relatedWork.map((w) => (
                  <WorkOrderCard key={w.id} wo={w} />
                ))}
              </div>
            </section>
          )}

          {selected && selected.closed_at && relatedWork.length === 0 && (
            <section className="panel">
              <div className="panel-body">
                <div className="banner is-info">
                  <div>
                    No work order. This incident resolved without sending anyone, which is
                    the saving rather than a gap in the record.
                  </div>
                </div>
                <div className="text-xs text-muted" style={{ marginTop: "var(--s-2)" }}>
                  Closed {ago(selected.closed_at)}
                </div>
              </div>
            </section>
          )}
        </div>
      </div>
    </main>
  );
}
