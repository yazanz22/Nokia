import { useState } from "react";
import { injectScenario, resetDemo } from "../lib/api";
import type { Asset } from "../types";

export function ScenarioPanel({ assets }: { assets: Asset[] }) {
  const eligible = assets.filter((a) => a.state === "healthy");
  const [assetId, setAssetId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>("");

  const target = assetId || eligible[0]?.id || "";

  const fire = async (scenario: string) => {
    if (!target) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await injectScenario(target, scenario);
      setMsg(`Injected ${scenario} on ${r.asset_id} (dataset row: ${r.dataset_label})`);
    } catch (e) {
      setMsg(`Error: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    try {
      await resetDemo();
      setMsg("Demo reset — fleet back to nominal.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="scenario">
      <select value={target} onChange={(e) => setAssetId(e.target.value)}>
        {eligible.length === 0 && <option value="">no healthy asset</option>}
        {eligible.map((a) => (
          <option key={a.id} value={a.id}>
            {a.id} — {a.label}
          </option>
        ))}
      </select>
      <div className="row">
        <button className="primary" disabled={busy || !target} onClick={() => fire("blindspot")}>
          Cellular blind spot
        </button>
        <button className="primary" disabled={busy || !target} onClick={() => fire("hardware")}>
          Hardware fault
        </button>
      </div>
      <button className="bad" disabled={busy} onClick={reset}>
        Reset demo
      </button>
      <div className="hint">
        Injects a real {`{NETWORK_OUTAGE | DEVICE_FAILURE}`} reading from the asset's dataset history,
        then stops its telemetry. The agent takes over autonomously.
      </div>
      {msg && <div className="hint">{msg}</div>}
    </div>
  );
}
