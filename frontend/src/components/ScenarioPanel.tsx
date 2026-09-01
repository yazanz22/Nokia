import { useState } from "react";
import { injectScenario, resetDemo } from "../lib/api";
import type { Asset } from "../types";

export function ScenarioPanel({ assets }: { assets: Asset[] }) {
  const eligible = assets.filter((a) => a.state === "healthy");
  const [assetId, setAssetId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>("");
  const [err, setErr] = useState<string>("");

  const target = assetId || eligible[0]?.id || "";

  const fire = async (scenario: string) => {
    if (!target) return;
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      const r = await injectScenario(target, scenario);
      setMsg(`${r.asset_id} went dark — replaying a real ${r.dataset_label} reading.`);
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

      <button className="btn ghost wide" disabled={busy} onClick={reset}>
        Reset fleet
      </button>

      {err && <div className="hint err">{err}</div>}
      {!err && msg && <div className="hint">{msg}</div>}
    </div>
  );
}
