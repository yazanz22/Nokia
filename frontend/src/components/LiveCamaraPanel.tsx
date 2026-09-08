import { useState } from "react";
import { runLiveCheck } from "../lib/api";

/** The house rule from lib/format.ts: words the operator uses, not the enum. */
const REACH_LABEL: Record<string, string> = {
  CONNECTED_DATA: "Connected, data",
  CONNECTED_SMS: "Connected, SMS only",
  NOT_CONNECTED: "Not connected",
  UNKNOWN: "Unknown",
};

interface LiveResult {
  endpoint_host: string;
  device: string;
  // Typed rather than `any`: these two are the calls the panel leads with, and
  // reading a coordinate off an unshaped response threw during render.
  device_status: {
    path: string;
    latency_ms: number;
    result: { status?: string; roaming?: boolean | null; country?: string | null };
  };
  location_retrieval: {
    path: string;
    latency_ms: number;
    result: { latitude?: number; longitude?: number; accuracy_m?: number };
  };
  congestion_insights?: CongestionCall;
  geofencing?: {
    path: string;
    status: string;
    subscription_id?: string;
    count?: number;
    note?: string;
    error?: string;
  };
}

/**
 * Congestion Insights is best-effort on the backend — it is issued inside the
 * reachability call and must never fail it — so it is the one family here that can come
 * back empty on its own. `returned` says whether it did, which is not the same question
 * as what the level was: "None" is a level the operator states and it means the serving
 * area is clear.
 */
interface CongestionCall {
  path: string;
  bundled_with: string;
  attempted?: boolean;
  returned?: boolean;
  /** The confidence floor the agent actually applied, sent by the backend so this panel
   *  never keeps a second copy of the number to drift out of step with. */
  min_confidence?: number;
  note?: string;
  result: { congestion_level?: string | null; confidence_level?: number | null };
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
      setErr(e instanceof Error ? e.message : String(e));
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
          Hits the Nokia sandbox for real: Device Reachability Status, Device Roaming
          Status, Congestion Insights and Location Retrieval, round-trip timed.
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
              {(() => {
                const st = String(res.device_status.result.status ?? "UNKNOWN");
                const ok = st.startsWith("CONNECTED");
                return (
                  <span className={`v ${ok ? "ok" : "bad"}`}>{REACH_LABEL[st] ?? st}</span>
                );
              })()}
            </div>
            {/* `!= null` rather than `!== null`: the field is optional on the wire,
                and `undefined !== null` printed the string "undefined". */}
            {res.device_status.result.roaming != null && (
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
            {/* The sandbox can answer 200 with a body that carries no fix. Reading
                a coordinate off it unguarded threw during render. */}
            {(() => {
              const loc = res.location_retrieval.result ?? {};
              const lat = typeof loc.latitude === "number" ? loc.latitude : null;
              const lon = typeof loc.longitude === "number" ? loc.longitude : null;
              const fix = lat !== null && lon !== null ? `${lat.toFixed(4)}, ${lon.toFixed(4)}` : null;
              return (
                <>
                  <div className="kv">
                    <span className="k">position</span>
                    <span className={`v ${fix ? "" : "quiet"}`}>
                      {fix ?? "no fix returned"}
                    </span>
                  </div>
                  <div className="kv">
                    <span className="k">accuracy</span>
                    <span className={`v ${typeof loc.accuracy_m === "number" ? "" : "quiet"}`}>
                      {typeof loc.accuracy_m === "number"
                        ? `±${Math.round(loc.accuracy_m)} m`
                        : "not reported"}
                    </span>
                  </div>
                </>
              );
            })()}
          </div>

          {res.congestion_insights && <CongestionBlock call={res.congestion_insights} />}

          {res.geofencing &&
            (() => {
              const registered =
                res.geofencing!.status === "existing" || res.geofencing!.status === "created";
              return (
                <div className={`live-call${registered ? "" : " live-call-empty"}`}>
                  <div className="live-call-head">
                    <span className={registered ? "badge-live" : "badge-quiet"}>
                      {registered ? "LIVE" : "NOT REGISTERED"}
                    </span>
                    <span className="path">Geofencing Subscriptions v0.3</span>
                    <span className="lat">push</span>
                  </div>
                  <div className="kv">
                    <span className="k">perimeter watch</span>
                    <span className={`v ${registered ? "" : "quiet"}`}>
                      {res.geofencing!.status}
                      {res.geofencing!.count ? ` · ${res.geofencing!.count}` : ""}
                      {res.geofencing!.subscription_id
                        ? ` · ${res.geofencing!.subscription_id.slice(0, 8)}`
                        : ""}
                    </span>
                  </div>
                  {res.geofencing!.note && (
                    <div className="hint" style={{ marginTop: "var(--s-1)" }}>
                      {res.geofencing!.note}
                    </div>
                  )}
                  {/* The backend sends the failure reason precisely so a reviewer
                      can see what broke. It was typed and never rendered. */}
                  {res.geofencing!.error && (
                    <div className="hint err" style={{ marginTop: "var(--s-1)" }}>
                      {res.geofencing!.error}
                    </div>
                  )}
                </div>
              );
            })()}

          <div className="hint">
            A real call to the Nokia sandbox. The test SIM is provisioned in Hungary. The fleet
            above is replayed telemetry served through the identical CAMARA contract.
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Congestion Insights, including when it has nothing to say.
 *
 * This block used to render only when a level came back, so a sandbox hiccup deleted it
 * from the panel with no trace — and this is the family that carries the argument: CAMARA
 * Device Status returns no signal strength and no neighbour-cell failures, so grading the
 * serving *area* is the only network-side evidence that a silence is coverage rather than
 * a breakdown. A presenter pointing at where it should be deserves to see the call
 * reported as attempted and empty, not to find a gap.
 */
function CongestionBlock({ call }: { call: CongestionCall }) {
  const level = call.result?.congestion_level ?? null;
  // Older responses carry neither flag; fall back to the shape of the reading itself.
  const returned = call.returned ?? level != null;
  const conf = call.result?.confidence_level ?? null;
  const floor = call.min_confidence;

  return (
    <div className={`live-call${returned ? "" : " live-call-empty"}`}>
      <div className="live-call-head">
        <span className={returned ? "badge-live" : "badge-quiet"}>
          {returned ? "LIVE" : "NO READING"}
        </span>
        <span className="path">Congestion Insights v0</span>
        <span className="lat">bundled</span>
      </div>

      <div className="kv">
        <span className="k">serving area</span>
        <span className={returned ? "v" : "v quiet"}>
          {returned ? `${level}${conf != null ? ` · ${conf}% confidence` : ""}` : "no reading"}
        </span>
      </div>

      {!returned && (
        <div className="hint" style={{ marginTop: 4 }}>
          {call.note ??
            "The call went out with the reachability check and returned nothing we could read, so the agent decides on the other signals."}
        </div>
      )}

      {returned && level === "None" && (
        <div className="hint" style={{ marginTop: 4 }}>
          “None” is the operator grading this area as clear — a reading, not a missing answer.
          Low congestion strengthens the hardware verdict rather than excusing it.
        </div>
      )}

      {returned && conf != null && floor != null && conf < floor && (
        <div className="hint" style={{ marginTop: 4 }}>
          Below the agent's {floor}% confidence floor, so it reports this and decides on other
          evidence. The sandbox returns a fresh synthetic reading per call.
        </div>
      )}
    </div>
  );
}
