import { useState } from "react";
import { runLiveCheck } from "../lib/api";

interface LiveResult {
  endpoint_host: string;
  device: string;
  device_status: { path: string; latency_ms: number; result: any };
  location_retrieval: { path: string; latency_ms: number; result: any };
}

/**
 * The "prove it's real" panel.
 *
 * The fleet on the map is a simulation of a NEOM-scale site. This calls the actual
 * Nokia Network as Code sandbox, live, and shows what comes back — including the
 * round-trip latency. Keeping the two visibly separate is the honest presentation:
 * the sandbox test SIM lives in Hungary and always reports reachable, so it cannot
 * stand in for thirty machines spread across a desert site.
 */
export function LiveCamaraPanel({ assetId }: { assetId: string | null }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<LiveResult | null>(null);
  const [err, setErr] = useState<string>("");

  const run = async () => {
    setBusy(true);
    setErr("");
    try {
      setRes(await runLiveCheck(assetId ?? undefined));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="live-camara">
      <button className="live-btn" disabled={busy} onClick={run}>
        {busy ? "Calling Nokia…" : "Run live CAMARA check"}
      </button>

      {err && <div className="hint err">{err}</div>}

      {res && (
        <div className="live-out">
          <div className="live-row">
            <span className="k">host</span>
            <span className="v mono">{res.endpoint_host}</span>
          </div>
          <div className="live-row">
            <span className="k">device</span>
            <span className="v mono">{res.device}</span>
          </div>

          <div className="live-call">
            <div className="live-call-head">
              <span className="badge-live">LIVE</span>
              <span className="mono path">Device Reachability Status v1</span>
              <span className="lat">{res.device_status.latency_ms} ms</span>
            </div>
            <div className="live-row">
              <span className="k">status</span>
              <span className="v ok">{res.device_status.result.status}</span>
            </div>
            {res.device_status.result.roaming !== null && (
              <div className="live-row">
                <span className="k">roaming</span>
                <span className="v">
                  {String(res.device_status.result.roaming)}
                  {res.device_status.result.country ? ` · ${res.device_status.result.country}` : ""}
                </span>
              </div>
            )}
          </div>

          <div className="live-call">
            <div className="live-call-head">
              <span className="badge-live">LIVE</span>
              <span className="mono path">Location Retrieval v0</span>
              <span className="lat">{res.location_retrieval.latency_ms} ms</span>
            </div>
            <div className="live-row">
              <span className="k">position</span>
              <span className="v mono">
                {res.location_retrieval.result.latitude.toFixed(4)},{" "}
                {res.location_retrieval.result.longitude.toFixed(4)}
              </span>
            </div>
            <div className="live-row">
              <span className="k">accuracy</span>
              <span className="v">±{Math.round(res.location_retrieval.result.accuracy_m)} m</span>
            </div>
          </div>

          <div className="hint">
            Real call to the Nokia sandbox. The test SIM is provisioned in Hungary — the
            NEOM fleet above is simulated telemetry served through the identical CAMARA
            contract.
          </div>
        </div>
      )}
    </div>
  );
}
