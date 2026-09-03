/** FastAPI puts the human-readable reason in `detail`; surface that, not raw JSON. */
async function failure(r: Response): Promise<Error> {
  try {
    const body = await r.json();
    if (typeof body?.detail === "string") return new Error(body.detail);
  } catch {
    /* not JSON — fall through */
  }
  return new Error(`Request failed (${r.status})`);
}

export async function injectScenario(assetId: string, scenario: string) {
  const r = await fetch("/api/scenarios/inject", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ asset_id: assetId, scenario }),
  });
  if (!r.ok) throw await failure(r);
  return r.json();
}

export async function resetDemo() {
  const r = await fetch("/api/scenarios/reset", { method: "POST" });
  if (!r.ok) throw await failure(r);
  return r.json();
}

export async function getHealth() {
  const r = await fetch("/api/debug/health");
  return r.json();
}

/** Predictive maintenance: which machines are trending toward failure. */
export async function getFleetHealth() {
  const r = await fetch("/api/fleet/health");
  if (!r.ok) throw await failure(r);
  return r.json();
}

/** Fires a genuine CAMARA call at the Nokia sandbox, regardless of NAC_MODE. */
export async function runLiveCheck(assetId?: string) {
  const q = assetId ? `?asset_id=${encodeURIComponent(assetId)}` : "";
  const r = await fetch(`/api/nac/live-check${q}`, { method: "POST" });
  if (!r.ok) throw await failure(r);
  return r.json();
}

/** Operator signs the repair off by hand instead of waiting out the auto-complete timer. */
export async function completeWorkOrder(id: string) {
  const r = await fetch(`/api/work-orders/${encodeURIComponent(id)}/complete`, { method: "POST" });
  if (!r.ok) throw await failure(r);
  return r.json();
}

/** Cancel a job outright — releases the technician and returns the machine to service. */
export async function deleteWorkOrder(id: string) {
  const r = await fetch(`/api/work-orders/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!r.ok) throw await failure(r);
  return r.json();
}
