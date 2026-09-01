import { useEffect, useRef } from "react";
import type { TraceStep } from "../types";

export function AgentTrace({ steps, active }: { steps: TraceStep[]; active: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [steps.length]);

  if (steps.length === 0)
    return (
      <div className="empty">
        <strong>Standing by</strong>
        <span>
          Monitoring every asset's heartbeat. The moment one stops, the agent opens an incident and
          starts investigating on its own — no operator involved.
        </span>
        <span>Its reasoning appears here, step by step, as it happens.</span>
      </div>
    );

  return (
    <div className="trace">
      {steps.map((s) => (
        <div className={`trace-step${s.tool ? " tool" : ""}`} key={`${s.incident_id}-${s.step}`}>
          <div className="n">{s.step}</div>
          <div>
            <div className="thought">{s.thought}</div>
            {s.tool && (
              <div className="tool-call">
                {s.tool}({fmtArgs(s.args)})
              </div>
            )}
            {s.observation && <div className="obs">{s.observation}</div>}
          </div>
        </div>
      ))}
      {active && (
        <div className="trace-step">
          <div className="n">
            <span className="pulse" style={{ color: "var(--hv)" }} />
          </div>
          <div className="thought" style={{ color: "var(--muted)" }}>
            thinking…
          </div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}

function fmtArgs(args: Record<string, unknown>): string {
  const keys = Object.keys(args);
  if (keys.length === 0) return "";
  return keys.map((k) => `${k}=${String(args[k])}`).join(", ");
}
