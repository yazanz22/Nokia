export async function injectScenario(assetId: string, scenario: string) {
  const r = await fetch("/api/scenarios/inject", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ asset_id: assetId, scenario }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function resetDemo() {
  const r = await fetch("/api/scenarios/reset", { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getHealth() {
  const r = await fetch("/api/debug/health");
  return r.json();
}

/** Predictive maintenance: which machines are trending toward failure. */
export async function getFleetHealth() {
  const r = await fetch("/api/fleet/health");
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/** Fires a genuine CAMARA call at the Nokia sandbox, regardless of NAC_MODE. */
export async function runLiveCheck(assetId?: string) {
  const q = assetId ? `?asset_id=${encodeURIComponent(assetId)}` : "";
  const r = await fetch(`/api/nac/live-check${q}`, { method: "POST" });
  if (!r.ok) throw new Error((await r.text()) || "live check failed");
  return r.json();
}
