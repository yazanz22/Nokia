import { useState } from "react";
import { injectScenario, resetDemo } from "../lib/api";
import type { Asset } from "../types";

export function ScenarioPanel({ assets }: { assets: Asset[] }) {
  const eligible = assets.filter((a) => a.state === "healthy");
  const [assetId, setAssetId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>("");
  const [err, setErr] = useState<string>("");

  // An injected asset stops being healthy, so it drops out of `eligible` — and a
  // `<select>` whose value matches no option renders blank, while the buttons kept
  // printing the stale id and every further click came back 409. A blank dropdown is
  // also the demo playbook's cue to hit "Reset fleet", which would wipe the KPI bar
  // mid-run. Fall back to the first still-eligible machine instead.
  const target = eligible.some((a) => a.id === assetId) ? assetId : eligible[0]?.id ?? "";

  const fire = async (scenario: string) => {
    if (!target) return;
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      const r = await injectScenario(target, scenario);
      setMsg(
        r.dataset_label === "OFFSITE_DRIFT"
          ? `${r.asset_id} is driving out of the site — it stays healthy the whole way.`
          : `${r.asset_id} went dark — replaying a real ${r.dataset_label} reading.`
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    setErr("");
    try {
      await resetDemo();
      setMsg("Fleet reset to nominal.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="scenario">
      <span className="field-label">Target asset</span>
      <select value={target} onChange={(e) => setAssetId(e.target.value)} disabled={busy}>
        {eligible.length === 0 && <option value="">no healthy asset</option>}
        {eligible.map((a) => (
          <option key={a.id} value={a.id}>
            {a.id} — {a.label}
          </option>
        ))}
      </select>

      <div className="btn-row">
        <button className="btn primary" disabled={busy || !target} onClick={() => fire("blindspot")}>
          Cellular blind spot
          <span className="target">{target || "—"}</span>
        </button>
        <button className="btn primary" disabled={busy || !target} onClick={() => fire("hardware")}>
          Hardware fault
          <span className="target">{target || "—"}</span>
        </button>
      </div>

      <button className="btn wide" disabled={busy || !target} onClick={() => fire("sensor")}>
        Sensor fault
        <span className="target">{target || "—"}</span>
      </button>

      {/* The two "the machine moved" scenarios share a row: five scenario buttons
          stacked full-width push the predictive-maintenance panel below the fold at
          1280x720, and these two are the pair that reads as a set. */}
      <div className="btn-row">
        <button className="btn" disabled={busy || !target} onClick={() => fire("roaming")}>
          Crossed the border (roaming)
          <span className="target">{target || "—"}</span>
        </button>
        <button className="btn" disabled={busy || !target} onClick={() => fire("offsite")}>
          Leaving the site (geofence)
          <span className="target">{target || "—"}</span>
        </button>
      </div>

      <button className="btn ghost wide" disabled={busy} onClick={reset}>
        Reset fleet
      </button>

      {err && <div className="hint err">{err}</div>}
      {!err && msg && <div className="hint">{msg}</div>}
    </div>
  );
}
