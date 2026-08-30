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
