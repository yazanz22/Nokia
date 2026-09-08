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
  if (!r.ok) throw await failure(r);
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

/** Warehouse stock across both depots, plus what is running low. */
export async function getInventory() {
  const r = await fetch("/api/inventory");
  if (!r.ok) throw await failure(r);
  return r.json();
}

/** Receipt a delivery (positive) or write stock off (negative) at one depot. */
export async function adjustStock(warehouseId: string, part: string, delta: number) {
  const r = await fetch(`/api/inventory/${encodeURIComponent(warehouseId)}/adjust`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ part, delta }),
  });
  if (!r.ok) throw await failure(r);
  return r.json();
}

/** The service board plus the machines where a service and a forecast coincide. */
export async function getMaintenanceSchedule() {
  const r = await fetch("/api/maintenance/schedule");
  if (!r.ok) throw await failure(r);
  return r.json();
}

/** Schedule the machine's due service. */
export async function raisePreventive(assetId: string) {
  const r = await fetch(`/api/maintenance/${encodeURIComponent(assetId)}/preventive`, {
    method: "POST",
  });
  if (!r.ok) throw await failure(r);
  return r.json();
}

/** Schedule a repair the forecast expects to need, optionally folding in the service. */
export async function raisePredictive(assetId: string, bundleService: boolean) {
  const q = bundleService ? "?bundle_service=true" : "";
  const r = await fetch(
    `/api/maintenance/${encodeURIComponent(assetId)}/predictive${q}`,
    { method: "POST" }
  );
  if (!r.ok) throw await failure(r);
  return r.json();
}

/**
 * The technician went, and there was nothing to fix.
 *
 * Deliberately not the same call as completing the job. Completing means the part
 * was fitted; this means the diagnosis was wrong, the component comes back to the
 * depot unused, and the wasted journey is counted.
 */
export async function closeNoFaultFound(id: string) {
  const r = await fetch(
    `/api/work-orders/${encodeURIComponent(id)}/no-fault-found`,
    { method: "POST" }
  );
  if (!r.ok) throw await failure(r);
  return r.json();
}
