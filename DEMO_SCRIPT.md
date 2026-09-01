# Live Demo Script — FILO Asset Sentinel

Phase 2 live demo, MENA Open Gateway Hackathon. **Target: 4 min 30 s**, leaving buffer inside a 5-minute
slot. Two people: a **driver** (laptop) and a **narrator** (speaks). Never the same person.

Everything below was verified end to end on 2026-09-01 against `main`. Numbers marked ≈ vary slightly
per run — **read what's on screen, don't recite from memory.**

---

## Locked decisions

| | |
|---|---|
| **Scenario order** | Blind spot **first**, hardware fault **second**. The first is the counter-intuitive win; the second is the payoff. |
| **Reset between scenarios?** | **No.** Running both without a reset leaves the KPI bar reading *1 false dispatch avoided · 1 dispatch issued* — the entire pitch in one frame. Reset only *before* you start. |
| **Scenario A asset** | `EQ-0295` — Haul Truck HT-295, Red Sea Global, Coastal Access Road |
| **Scenario B asset** | `EQ-0180` — Loader LD-180, NEOM, Trojena Ridge |
| **Modes** | See "Pre-flight" — decide `NAC_MODE` / `AGENT_MODE` before you walk in, not on stage. |

Why those two assets: a **haul truck** is mobile, so "it drove into a dead zone" is intuitive. A
**loader** sits and works, so "it didn't go anywhere, it overheated" is equally intuitive. The contrast
does narrative work for you.

---

## Pre-flight (T-10 min, before you're on stage)

```bash
pwsh scripts/dev.ps1
```

- [ ] Backend health returns your intended modes — `curl http://127.0.0.1:8000/api/debug/health`
- [ ] Dashboard open at `http://127.0.0.1:5173`, browser zoomed so the **three columns** all fit
- [ ] **Reset demo** clicked — KPI bar reads `100.0%` / `30/30` / all zeros
- [ ] Notifications off, Do Not Disturb on, Slack and mail closed
- [ ] `EQ-0295` selected in the dropdown, ready for the first click

> The scenario buttons print their target asset ID underneath them. **Check the button says the asset
> you mean before every click** — the dropdown resets to the first healthy asset after each injection.

---

## 0:00 – 0:30 · The problem

> "A giga-project like NEOM runs hundreds of machines across thousands of square kilometres. When one
> of them stops sending telemetry, the site manager has no idea why. Did it break down? Did the sensor
> die? Or did it just drive into a cellular dead zone?
>
> Today the answer is: send someone and find out. That's a two-hour drive across the desert to
> *maybe* stand next to a perfectly healthy excavator that simply lost signal."

**Driver:** dashboard on screen, nothing clicked yet.

---

## 0:30 – 1:00 · What you're looking at

> "This is our operations dashboard. Thirty machines on a live site, streaming telemetry — engine
> temperature, signal strength, network health. Everything is green. Fleet availability 100%.
>
> Watch what happens when one of them goes dark."

**Driver:** point at the map, then the KPI bar. Don't click yet.

---

## 1:00 – 2:00 · Scenario A — the machine that was fine

**Driver:** confirm the buttons read `EQ-0295` → click **Cellular blind spot**.

> "Haul truck HT-295, out on the Red Sea coastal access road. Its telemetry stream just stopped."

*(≈2 s — the asset turns red on the map, an incident opens.)*

> "No human touched anything. The agent has already opened an incident and it's doing what a site
> manager can't do from an office: it's asking the **network** whether the truck is reachable — a live
> CAMARA Device Status call through Nokia Network as Code."

**Driver:** trace the reasoning panel with the cursor as steps appear.

> "And here's the interesting part. The device comes back **not connected** — which normally means
> 'send a mechanic'. But the agent doesn't stop there. Last serving-cell signal: **≈ −127 dBm**.
> Twelve neighbouring cells failing at the same time.
>
> That is not a broken machine. That is a hole in the coverage. The truck is almost certainly fine —
> it just drove out of range."

*(≈4 s total — incident closes as BLIND SPOT · NO DISPATCH.)*

> "So the agent logs a cellular blind spot, schedules an automatic re-check, notifies the operator —
> **and dispatches nobody.**"

**Driver:** point at **Work orders — "No work orders issued"**, then the KPI **False dispatches avoided: 1**.

> "That right there is the forty percent of field trips that never needed to happen."

---

## 2:00 – 3:20 · Scenario B — the machine that wasn't

**Driver:** select `EQ-0180` in the dropdown. **Confirm both buttons now read `EQ-0180`.** Click
**Hardware fault**.

> "Now a different machine. Loader LD-180, up at Trojena Ridge. Same symptom exactly — telemetry
> stops, and the network again reports the device as **not connected**.
>
> Identical symptom. Completely different cause."

*(watch the trace)*

> "Look at the signal this time: **≈ −53 dBm**, strong. **Zero** neighbouring cell failures. The
> network here is perfectly healthy — so the silence is the machine itself.
>
> Now the agent brings in the ML model, trained on our fleet telemetry. Engine temperature far above
> the safe envelope while the radio link was fine: **device failure, 93% confidence** — a hydraulic
> pump."

**Driver:** as the location step lands, point at the map — the dispatch route line draws itself.

> "The on-board GPS is dark, so the agent makes its second network call: **CAMARA Location Retrieval**
> — network-verified coordinates, straight from the operator, for a device that can't report its own
> position.
>
> And it closes the loop: work order raised, nearest qualified technician assigned — Omar Farouk,
> ≈21 km out, ≈38 minutes — carrying the exact part, a `HYD-PUMP-40L`."

**Driver:** point at the work-order card.

> "Six seconds, from telemetry going dark to a technician routed with the right part in the truck.
> No human in the loop at any point."

---

## 3:20 – 4:00 · The numbers, and how it works

**Driver:** point at the KPI bar — it now reads **1 false dispatch avoided · 1 dispatch issued**.

> "Same symptom, two opposite correct decisions. That's the whole product.
>
> Underneath: an AI agent with the CAMARA APIs registered as **tools it decides when to call** — not
> buttons a person presses. Device Status is the network truth layer. Location Retrieval is the
> dispatch layer. Both through Nokia Network as Code, GSMA Open Gateway compliant.
>
> At fleet scale that's **40% fewer wasted dispatches, 25% less downtime, 15% off operating cost** —
> and measurably fewer crew-hours spent driving across the desert in extreme heat."

---

## 4:00 – 4:30 · Close

> "Every alert is validated against network truth before anyone is sent anywhere. It scales across
> NEOM, Red Sea Global, Qiddiya, Masdar — anywhere assets outrun coverage.
>
> We're ready to pilot this on live fleet data with a regional operator — STC, Mobily, or e&.
>
> Thank you."

**Driver:** leave the final frame up — both incidents in the feed, KPI bar showing both outcomes.

---

## Recovery playbook

| Symptom | Fix |
|---|---|
| Scenario button does nothing | Check the button's target ID. If the dropdown is empty, click **Reset demo**. |
| Trace stalls part-way (LLM mode) | Say *"switching to our deterministic path"* — set `AGENT_MODE=rule` in `.env`, restart backend. Identical on screen. |
| Dashboard shows "reconnecting…" | Backend died. Restart it (below); the dashboard reconnects on its own. |
| KPIs/state look stale or wrong | Click **Reset demo**, re-run from Scenario A. |
| Everything is broken | Cut to the backup video. Do not debug on stage. |

**Restarting the backend on Windows** — `pkill` does *not* match `python.exe -m uvicorn`, so the old
process keeps port 8000 and the new one silently fails to bind:

```bash
netstat -ano | grep ":8000.*LISTENING"
```

Take the PID from that output, then:

```bash
taskkill //PID <PID> //F
```

Then restart via `scripts/dev.ps1`.

---

## Q&A — likely questions

**"Is this really calling Nokia's API, or is it simulated?"**
Answer honestly, and know which mode you're in before you're asked. In `live` mode these are real
sandbox calls — offer to show `GET /api/debug/nac?asset_id=EQ-0180`, which returns
`effective_source: "live"`. In `mock` mode: the adapter is the same code path against the same CAMARA
contract; we swap one environment variable, and we fall back to cached data automatically if the venue
network drops — which is exactly what you'd want in production too.

**"Where did the training data come from?"**
Synthetic, generated by `data/dataset_builder.py` — 15,000 readings across 500 assets. We model four
states with distinct network signatures. Note the honest part: `NORMAL` and `SENSOR_FAILURE` deliberately
overlap, so the model does *not* score 100% — it genuinely confuses some sensor faults with healthy
readings. What it separates cleanly is the decision that actually matters: coverage gap vs hardware
failure.

**"Why not just use GPS from the machine?"**
Because the machine is the thing that went silent. If the telemetry uplink is down, its GPS is down
too. Network-side location is the only position source that still works — and it can't be spoofed by a
compromised device.

**"What if the network says connected but the machine is fine?"**
Then the ML model returns `NORMAL` or `SENSOR_FAILURE` and we raise a low-cost sensor-kit job instead
of a mechanic. Not every dispatch is a pump.

**"Which part of this is the AI agent, exactly?"**
The orchestration. The agent decides *whether* to call Device Status, *how to weigh* conflicting
signals — unreachable but strong signal is the hard case — *whether* the ML model is even relevant,
and *whether* to spend a dispatch. Pydantic AI with a Groq-hosted Llama 3.3 70B; the CAMARA endpoints
are registered as tools it chooses to invoke.

**"How is this different from existing fleet telematics?"**
Telematics tells you a machine stopped reporting. It cannot tell you *why*, because it only sees the
device side. We add the operator's own view of the network as a second, independent source of truth —
and that's the signal that separates a dead engine from a dead cell.
