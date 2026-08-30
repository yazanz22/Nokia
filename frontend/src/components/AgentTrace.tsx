import { useEffect, useRef } from "react";
import type { TraceStep } from "../types";

export function AgentTrace({ steps }: { steps: TraceStep[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [steps.length]);

  if (steps.length === 0)
    return (
      <div className="trace-empty">
        No active investigation. Trigger a scenario and the agent's reasoning appears here, step by step.
      </div>
    );

  return (
    <div>
      {steps.map((s) => (
        <div className="trace-step" key={`${s.incident_id}-${s.step}`}>
          <div className="n">{s.step}</div>
          <div>
            <div className="thought">{s.thought}</div>
            {s.tool && (
              <div className="tool">
                → {s.tool}({fmtArgs(s.args)})
              </div>
            )}
            {s.observation && <div className="obs">{s.observation}</div>}
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}

function fmtArgs(args: Record<string, unknown>): string {
  const keys = Object.keys(args);
  if (keys.length === 0) return "";
  return keys.map((k) => `${k}=${String(args[k])}`).join(", ");
}
