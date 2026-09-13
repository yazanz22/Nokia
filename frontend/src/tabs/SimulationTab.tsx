import { useState } from "react";
import { ArrowsClockwise, Broadcast } from "@phosphor-icons/react";
import { injectScenario, resetDemo } from "../lib/api";
import { LiveCamaraPanel } from "../components/LiveCamaraPanel";
import { plural } from "../lib/format";
import type { LiveState } from "../lib/ws";

const SCENARIOS = [
  {
    id: "blindspot",
    label: "Cellular blind spot",
    outcome: "No dispatch",
    body: "The machine goes quiet inside a coverage hole. The network says it is unreachable, the radio metrics say the cell was failing, and the agent sends nobody.",
  },
  {
    id: "hardware",
    label: "Hardware fault",
    outcome: "Technician sent",
    body: "The same silence, with a healthy radio link behind it. The network is ruled out, the model names the component, and a technician is routed via the depot that stocks the part.",
  },
  {
    id: "sensor",
    label: "Sensor fault",
    outcome: "Technician sent",
    body: "The machine is fine; the thing reporting on it is not. Worth a technician carrying a sensor kit, which rides in the van, so there is no depot stop.",
  },
  {
    id: "roaming",
    label: "Crossed the border",
    outcome: "No dispatch",
    body: "Reachable, healthy, and attached to a Jordanian operator. Its telemetry no longer routes to us. A connectivity ticket, not a mechanic.",
  },
  {
    id: "offsite",
    label: "Leaving the site",
    outcome: "Incident prevented",
    body: "A healthy machine drives west across the perimeter. The operator's geofence pushes the crossing to us while it is still reporting, so the silence never happens.",
  },
] as const;

/**
 * The controls that drive a demonstration, kept apart from the product.
 *
 * Nothing on this tab exists in a real deployment: a real site does not have a
 * button that breaks an excavator. Separating it is honesty as much as tidiness,
 * because a judge seeing scenario buttons beside live KPIs cannot tell which
 * numbers were earned. The live CAMARA check sits here for the same reason: it
 * is proof for a reviewer rather than a working surface for a dispatcher.
 */
export function SimulationTab({
  state,
  selectedAsset,
}: {
  state: LiveState;
  selectedAsset: string | null;
}) {
  const assets = Object.values(state.assets);
  const eligible = assets.filter((a) => a.state === "healthy");

  const [assetId, setAssetId] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  // An injected machine stops being healthy and drops out of `eligible`, and a
  // <select> whose value matches no option renders blank while the buttons keep
  // printing the stale id. Fall back to the first still-eligible machine.
  const target = eligible.some((a) => a.id === assetId) ? assetId : (eligible[0]?.id ?? "");

  const fire = async (scenario: string) => {
    if (!target) return;
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      const r = await injectScenario(target, scenario);
      setMsg(
        r.dataset_label === "OFFSITE_DRIFT"
          ? `${r.asset_id} is driving out of the site. It stays healthy the whole way.`
          : `${r.asset_id} went dark, replaying a real ${r.dataset_label} reading.`
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
    setMsg("");
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
    <main className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Simulation</h1>
          <p className="page-sub">
            Controls for demonstrating the system. None of this ships to a site: a real
            deployment has no button that breaks an excavator. Kept on its own tab so
            nothing on the other five is ambiguous about where its numbers came from.
          </p>
        </div>
        <button className="btn" onClick={reset} disabled={busy}>
          <ArrowsClockwise size={14} aria-hidden />
          Reset fleet
        </button>
      </div>

      {err && (
        <div className="banner is-bad" role="alert">
          {err}
        </div>
      )}
      {!err && msg && (
        <div className="banner is-info" role="status">
          {msg}
        </div>
      )}

      <section className="panel">
        <div className="panel-head">
          <h2>Inject a scenario</h2>
          <span className="panel-note">{plural(eligible.length, "healthy machine")} available</span>
        </div>
        <div className="panel-body stack">
          <div className="field" style={{ maxWidth: 380 }}>
            <label className="field-label" htmlFor="sim-target">
              Target machine
            </label>
            <select
              id="sim-target"
              className="select"
              value={target}
              onChange={(e) => setAssetId(e.target.value)}
              disabled={busy}
            >
              {eligible.length === 0 && <option value="">No healthy machine</option>}
              {eligible.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.id} {a.label}
                </option>
              ))}
            </select>
            <span className="field-help">
              The dropdown falls back to the next healthy machine after each injection, so
              every button prints the machine it will actually hit.
            </span>
          </div>

          <div className="scenario-grid">
            {SCENARIOS.map((s) => (
              <div className="scenario-card" key={s.id}>
                <div className="scenario-head">
                  <h3>{s.label}</h3>
                  <span
                    className={`badge ${
                      s.outcome === "No dispatch"
                        ? "is-ok"
                        : s.outcome === "Incident prevented"
                          ? "is-info"
                          : "is-warn"
                    }`}
                  >
                    {s.outcome}
                  </span>
                </div>
                <p className="scenario-body">{s.body}</p>
                <button
                  className="btn btn-primary"
                  disabled={busy || !target}
                  onClick={() => fire(s.id)}
                  aria-label={`${s.label}: run on ${target || "nothing"}`}
                >
                  Run on <span className="mono">{target || "nothing"}</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <Broadcast size={15} aria-hidden />
          <h2>Live CAMARA check</h2>
          <span className="panel-note">Nokia Network as Code sandbox</span>
        </div>
        <div className="panel-body">
          <p className="text-sm text-muted" style={{ maxWidth: "78ch", marginBottom: "var(--s-3)" }}>
            Real calls to the Nokia Network as Code sandbox, showing the endpoint paths and
            the round-trip time we measured for each call. The fleet and technician crews on
            the other tabs are simulated, because the sandbox provides a few test SIMs located
            in Hungary. The network integration is the same code path either way, one
            environment variable apart.
          </p>
          <LiveCamaraPanel assetId={selectedAsset} />
        </div>
      </section>
    </main>
  );
}
