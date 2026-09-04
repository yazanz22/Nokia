import { useState } from "react";
import { runLiveCheck } from "../lib/api";

interface LiveResult {
  endpoint_host: string;
  device: string;
  device_status: { path: string; latency_ms: number; result: any };
  location_retrieval: { path: string; latency_ms: number; result: any };
  congestion_insights?: { path: string; bundled_with: string; result: any };
}

/**
 * The "prove it's real" panel.
 *
 * The fleet on the map is a simulation of a NEOM-scale site. This calls the actual
 * Nokia Network as Code sandbox and shows what comes back, latency included.
 * Keeping the two visibly separate is the honest presentation: the sandbox test SIM
 * lives in Hungary and always reports reachable, so it cannot stand in for thirty
 * machines spread across a desert site.
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
    <div>
      <button className="btn wide" disabled={busy} onClick={run}>
        {busy ? "Calling Nokia…" : "Run live CAMARA check"}
      </button>

      {err && <div className="hint err" style={{ marginTop: 8 }}>{err}</div>}

      {!res && !err && (
        <div className="hint" style={{ marginTop: 8 }}>
          Hits the Nokia sandbox for real — Device Reachability Status, Device Roaming Status,
          Congestion Insights and Location Retrieval, round-trip timed.
        </div>
      )}

      {res && (
        <div className="live-out">
          <div className="kv">
            <span className="k">host</span>
            <span className="v">{res.endpoint_host}</span>
          </div>
          <div className="kv">
            <span className="k">device</span>
            <span className="v">{res.device}</span>
          </div>

          <div className="live-call">
            <div className="live-call-head">
              <span className="badge-live">LIVE</span>
              <span className="path">Device Reachability Status v1</span>
              <span className="lat">{res.device_status.latency_ms} ms</span>
            </div>
            <div className="kv">
              <span className="k">status</span>
              <span className="v ok">{res.device_status.result.status}</span>
            </div>
            {res.device_status.result.roaming !== null && (
              <div className="kv">
                <span className="k">roaming</span>
                <span className="v">
                  {String(res.device_status.result.roaming)}
                  {res.device_status.result.country
                    ? ` · ${res.device_status.result.country}`
                    : ""}
                </span>
              </div>
            )}
          </div>

          <div className="live-call">
            <div className="live-call-head">
              <span className="badge-live">LIVE</span>
              <span className="path">Location Retrieval v0</span>
              <span className="lat">{res.location_retrieval.latency_ms} ms</span>
            </div>
            <div className="kv">
              <span className="k">position</span>
              <span className="v">
                {res.location_retrieval.result.latitude.toFixed(4)},{" "}
                {res.location_retrieval.result.longitude.toFixed(4)}
              </span>
            </div>
            <div className="kv">
              <span className="k">accuracy</span>
              <span className="v">
                ±{Math.round(res.location_retrieval.result.accuracy_m)} m
              </span>
            </div>
          </div>

          {res.congestion_insights?.result?.congestion_level && (
            <div className="live-call">
              <div className="live-call-head">
                <span className="badge-live">LIVE</span>
                <span className="path">Congestion Insights v0</span>
                <span className="lat">bundled</span>
              </div>
              <div className="kv">
                <span className="k">serving area</span>
                <span className="v">
                  {res.congestion_insights.result.congestion_level}
                  {res.congestion_insights.result.confidence_level != null
                    ? ` · ${res.congestion_insights.result.confidence_level}% confidence`
                    : ""}
                </span>
              </div>
              {res.congestion_insights.result.confidence_level != null &&
                res.congestion_insights.result.confidence_level < 50 && (
                  <div className="hint" style={{ marginTop: 4 }}>
                    Below our 50% confidence floor, so the agent reports this and decides on other
                    evidence. The sandbox returns a fresh synthetic reading per call.
                  </div>
                )}
            </div>
          )}

          <div className="hint">
            A real call to the Nokia sandbox. The test SIM is provisioned in Hungary — the fleet
            above is replayed telemetry served through the identical CAMARA contract.
          </div>
        </div>
      )}
    </div>
  );
}
