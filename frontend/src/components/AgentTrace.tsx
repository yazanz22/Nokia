import { ArrowRight, CheckCircle, CircleNotch } from "@phosphor-icons/react";
import type { Incident, TraceStep } from "../types";
import { href } from "../lib/router";
import { EmptyState } from "./StateBlock";

/**
 * The agent's reasoning, in two depths.
 *
 * `AgentStatus` is what the dashboard shows: what the agent is doing right now
 * and what it concluded, and nothing else. The full transcript is a reading
 * surface, not a monitoring one, so it lives on the Incidents tab. A dispatcher
 * watching a site does not read paragraphs; they want to know whether the thing
 * has been settled and whether anyone has to move.
 */

function verdict(incident: Incident | undefined): { label: string; tone: string } | null {
  if (!incident || !incident.closed_at) return null;
  switch (incident.status) {
    case "network_blindspot":
      return { label: "Coverage gap. Nobody dispatched.", tone: "is-info" };
    case "roaming_blocked":
      return { label: "Roamed abroad. Nobody dispatched.", tone: "is-info" };
    case "no_fault":
      return { label: "Transient dropout. Nobody dispatched.", tone: "is-ok" };
    case "sensor_confirmed":
      return { label: "Sensor fault. Technician sent with a kit.", tone: "is-warn" };
    case "hardware_confirmed":
      return { label: "Hardware fault confirmed. Technician sent.", tone: "is-bad" };
    case "awaiting_crew":
      return { label: "Confirmed, waiting for a free technician.", tone: "is-warn" };
    case "awaiting_part":
      return { label: "Confirmed, waiting for a part.", tone: "is-warn" };
    default:
      return { label: "Closed.", tone: "" };
  }
}

/** Dashboard depth: one line of activity, one line of outcome, one link out. */
export function AgentStatus({
  incident,
  steps,
}: {
  incident: Incident | undefined;
  steps: TraceStep[];
}) {
  if (!incident) {
    return (
      <EmptyState
        icon={CheckCircle}
        title="Nothing to investigate"
        body="Every machine is reporting. When one goes quiet the agent opens an incident here on its own."
      />
    );
  }

  const running = incident.closed_at === null;
  const outcome = verdict(incident);
  const latest = steps[steps.length - 1];

  return (
    <div className="agent-status">
      <div className="agent-status-head">
        {/* "Settled" is not itself good or bad news, so the badge stays neutral and
            the verdict below carries the colour. A red badge reading "Settled" was
            the first thing that looked like an error when nothing had gone wrong. */}
        <span className={`badge ${running ? "is-warn" : ""}`}>
          {running ? "Investigating" : "Settled"}
        </span>
        <span className="mono text-xs text-muted">{incident.id}</span>
      </div>

      <p className={`agent-status-line${outcome && !running ? ` tone-${outcome.tone}` : ""}`}>
        {running ? (
          <>
            <CircleNotch size={14} className="agent-spin" aria-hidden />
            {latest?.tool ? toolLabel(latest.tool) : "Opening the incident"}
          </>
        ) : (
          outcome?.label
        )}
      </p>

      <div className="agent-status-meta text-xs text-muted">
        {steps.length} {steps.length === 1 ? "step" : "steps"}
      </div>

      <a className="btn btn-sm" href={href("incidents", incident.id)}>
        Read the full reasoning
        <ArrowRight size={13} aria-hidden />
      </a>
    </div>
  );
}

/** Turn a tool id into something a site manager reads without a glossary. */
function toolLabel(tool: string): string {
  const map: Record<string, string> = {
    "camara.device_status": "Asking the network whether the device is reachable",
    "camara.roaming_status": "Checking whether it roamed onto another network",
    "camara.congestion_insights": "Checking how congested the serving area is",
    "camara.location_retrieval": "Getting network-verified coordinates",
    "ml.predict_fault": "Classifying the fault",
    "ml.identify_component": "Identifying the failing component",
    "ops.create_work_order": "Raising the work order",
    "ops.notify_operator": "Notifying the operator",
  };
  return map[tool] ?? tool;
}

/** Incidents-tab depth: every step, with what it called and what came back. */
export function AgentTrace({ steps, active }: { steps: TraceStep[]; active: boolean }) {
  if (steps.length === 0) {
    return (
      <EmptyState
        title="No reasoning recorded"
        body="This incident closed before the agent narrated a step, or the trace was cleared by a fleet reset."
      />
    );
  }

  return (
    <ol className="trace">
      {steps.map((s) => (
        <li className="trace-step" key={s.step}>
          <div className="trace-marker" aria-hidden />
          <div className="trace-content">
            <p className="trace-thought">{s.thought}</p>
            {s.tool && (
              <div className="trace-tool">
                {/* The raw id stays visible, because auditability is the point of
                    this surface. The plain-English name is attached for speech,
                    where "camara.device_status" is unintelligible. */}
                <span className="mono" aria-label={toolLabel(s.tool)}>
                  {s.tool}
                </span>
                {s.observation && <span className="trace-obs">{s.observation}</span>}
              </div>
            )}
          </div>
        </li>
      ))}
      {active && (
        <li className="trace-step is-running">
          <div className="trace-marker" aria-hidden />
          <div className="trace-content">
            <p className="trace-thought text-muted">
              <CircleNotch size={13} className="agent-spin" aria-hidden /> Working
            </p>
          </div>
        </li>
      )}
    </ol>
  );
}
