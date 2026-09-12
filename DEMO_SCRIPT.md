# Demo Script — FILO Asset Sentinel

Recorded demo video, MENA Open Gateway Hackathon. **Target: 5:30.** Two people: a **driver**
(laptop) and a **narrator** (speaks). Never the same person.

Four things to land, in this order: **we don't send anyone we don't need to** (blind spot), **when we
do send someone it's right first time** (hardware + component + the right part), **we see failures
coming days out** (predictive), and **some silences never happen at all** (perimeter). The live
CAMARA check, run on the public Render deployment, is the proof that the network layer is real.

Numbers marked ≈ vary per run. **Read what's on screen, don't recite from memory.**

> **Rehearsed 2026-09-13 against `ee240a1`** on one local server (`AGENT_MODE=llm`,
> `groq:openai/gpt-oss-120b`, `NAC_MODE=mock`) at 1440×900, plus the live check on
> https://nokia-rhhp.onrender.com. Every quoted on-screen line below comes from that run. If the
> build changes, dry-run again and re-stamp this note.

---

## Locked decisions

| | |
|---|---|
| **Scenario order** | Blind spot **first** (counter-intuitive win), hardware **second** (the payoff), predictive **third**, perimeter **fourth**. |
| **Roaming scenario** | **Cut from the video.** In rehearsal the LLM agent reached the right verdict but ran the fault classifier on the way, so "Read the full reasoning" showed a `SENSOR_FAILURE @ 100%` step before the roaming ticket. It still exists on the Simulation tab and is covered in Q&A. |
| **Reset between scenarios?** | **No.** Reset only *before* you start. The final KPI bar then reads *Dispatches avoided 1 · Incidents prevented 1 · Dispatches issued 1*. |
| **Scenario A asset** | `EQ-0295` — Welder Set WS-295, Red Sea Global, Coastal Access Road |
| **Scenario C asset** | `EQ-0180` — Pump Set PS-180, NEOM, Trojena Ridge |
| **Scenario D asset** | `EQ-0233` — Generator GN-233, Red Sea Global, Coastal Access Road. **Use this one and no other.** It crossed the perimeter **35 s** after injection in rehearsal (34 s measured previously). Crossing time depends on where a machine starts, and other machines cross anywhere from about 10 s to about 1 min. The forecasting model scores it **not at risk**, so "nothing is wrong with this one" is true on both counts. |
| **Live CAMARA check** | On **Render**, not localhost. Locally `PUBLIC_BASE_URL` is unset, so the panel shows geofencing `NOT REGISTERED · needs public url`. On Render it showed `LIVE · existing · 1 · e676b693`. |
| **Model** | `groq:openai/gpt-oss-120b`. `groq:qwen/qwen3.8-27b` is the fallback if Groq degrades the first. |

Why those assets: every machine on this fleet is **unattended plant**: gensets, pump sets,
compressors, light towers, power packs, welder sets. It is worth one sentence on camera, because the
obvious objection is *"doesn't somebody sit in it?"* Nobody sits in any of these. When one goes quiet
there is no operator to radio in.

A **welder set** is repositioned as the works move, so "it ended up parked where the network doesn't
reach" is intuitive. A **pump set** is dropped once and runs for weeks, so "it hasn't gone anywhere,
it broke" is equally intuitive. Same symptom, opposite cause.

> ### ⚠️ Groq has a 200,000 token-per-day cap on the free tier
>
> It fails *quietly*: every investigation falls back to the rule agent with
> `last_agent_used: "rule (fallback)"`, and the output on screen is identical and correct. **Check
> `last_agent_used` in `/api/debug/health` immediately before you record.** Budget roughly 5–8k
> tokens per investigation.

---

## The app is tabbed — know where everything is

A new incident does **not** switch tabs; it only badges the **Incidents** tab. The driver moves.

| Tab | What you use there |
|---|---|
| **Dashboard** | KPI bar, Site map, **Agent** (one-line verdict + "Read the full reasoning"), **Perimeter** (appears only after a crossing), **Open work orders** |
| **Simulation** | "Target machine" dropdown, five cards each with **Run on EQ-xxxx**, **Reset fleet**, Live CAMARA check |
| **Maintenance** | Predictive / Preventive / Corrective. Predictive shows "One visit, not two" then **Forecast failures** (Expected · Vibration · Oil particles · Schedule) |
| **Assets** | Fleet table; click an ID to fill **Detail** (state badges, explanation, Last telemetry) |
| **Incidents** | Record, **Agent reasoning** (every step), Work raised |

The cards are **Cellular blind spot**, **Hardware fault**, **Sensor fault**, **Crossed the border**,
**Leaving the site**. The dropdown falls back to the first healthy machine after every injection, and
every button prints the machine it will hit. **Check the button before every click.**

---

## Pre-flight (before recording)

```bash
cd frontend && npm run build
```

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000
```

- [ ] `curl http://127.0.0.1:8000/api/debug/health` shows `agent_mode: llm`, `ml_backend: trained`,
      `live_camara_available: true`
- [ ] **`last_agent_used` is `llm`.** A freshly started server reads `none` until *it* has
      investigated something. Inject one scenario on `EQ-0027`, let it settle, check. The value
      survives a reset but not a restart, so **do not restart after this**
- [ ] Recording window **wider than 1100px** (rehearsed at 1440×900). At 1100px and below the
      dashboard is single-column and the work-order card falls below the map
- [ ] **Reset with memory cleared**, or Scenario A opens with "I've seen this before":

```bash
curl -X POST "http://127.0.0.1:8000/api/scenarios/reset?clear_memory=true"
```

- [ ] KPI bar reads `100.0%` / `30 of 30 machines` / all zeros / Average triage `n/a`
- [ ] Maintenance → Forecast failures lists machines (not "The forecast is unavailable"). Note the top
      row. In rehearsal it was **EQ-0248 Welder Set WS-248, 24h, +1.76, +343**. Several machines tie at
      24h, so name whatever is on top
- [ ] **Second browser tab:** https://nokia-rhhp.onrender.com/?cb=1#/simulation — open it a few
      minutes early; the free plan sleeps and takes about a minute to wake
- [ ] Simulation tab, `EQ-0295` selected, button reads **Run on EQ-0295**
- [ ] Notifications off, Do Not Disturb on, Slack and mail closed

### Things that move on their own

- **Investigations are fast.** In rehearsal: blind spot **5.7 s**, hardware **12 s**, dark to decided.
  By the time you switch to the Dashboard the verdict may already be there. Narrate over the result.
- **Work orders auto-complete 90 s after they are raised.** In rehearsal the C card was gone before
  the predictive beat ended. Point at the card straight away. The KPI "Dispatches issued" stays at 1.
- **Technicians drift across the map** every tick. That is the point of locating them over the network.

---

## 0:00 – 0:30 · The problem

> "A giga-project like NEOM runs hundreds of machines across thousands of square kilometres, and most
> of them run unattended — generators, pumps, compressors. When one stops sending telemetry, the site
> manager has no idea why. Did it break? Did the sensor die? Did it end up in a cellular dead zone?
>
> The data that would tell you is the data that just stopped arriving. You cannot diagnose a silent
> machine from the machine.
>
> So today the answer is: send someone and find out. A long drive across the desert to *maybe* stand
> next to a perfectly healthy generator that simply lost signal."

**Driver:** Dashboard on screen, nothing clicked.

---

## 0:30 – 0:55 · What you're looking at

> "Our operations dashboard. Thirty machines on a live site, streaming telemetry. Fleet availability
> 100%, thirty of thirty.
>
> The triangles are field technicians — they move, because crews drive between jobs. The dark squares
> are parts depots. And the ringed machines are ones the forecasting model expects to fail — we'll come
> back to those.
>
> Now watch what happens when a machine goes dark."

**Driver:** point at the map, the technician markers, a depot, then the KPI bar.

> **Don't say "vibration" here.** The live telemetry panel shows engine temperature, signal,
> neighbour failures and telemetry age. Vibration and oil particles appear in the predictive beat.

---

## 0:55 – 1:45 · Scenario A — the machine that was fine

**Driver:** Simulation tab. Confirm **Run on EQ-0295** on the **Cellular blind spot** card → click →
**Dashboard**.

> "Welder set WS-295, on the Red Sea coastal access road. Nobody works it — it runs on its own.
> Telemetry just stopped."

*(the machine turns blue — No coverage; the Agent panel shows the incident)*

> "Nobody touched anything. The agent opened an incident and did what a site manager can't do from an
> office: asked the **network** whether the machine is reachable — a CAMARA Device Status call through
> Nokia Network as Code."

**Driver:** click **Read the full reasoning** (opens Incidents → Agent reasoning).

> "The device comes back **not connected** — which normally reads as 'send a mechanic'. But look at
> the agent's own reasoning: last serving-cell signal **≈ −127 dBm**, **≈12** neighbouring cells
> failing at the same time. The network dropped the device — nothing is wrong with the machine."

*(Agent panel on Dashboard: "Coverage gap. Nobody dispatched.")*

> "So it logs a cellular blind spot, schedules an automatic re-check, notifies the operator — **and
> dispatches nobody.**"

**Driver:** back to **Dashboard**. Point at **Open work orders — "Nobody is out"**, then KPI
**Dispatches avoided: 1**.

> "That's the field trip that never needed to happen."

> The KPI also prints "$250 to $600 saved (illustrative)". It is labelled illustrative on screen;
> don't read it out as a measured saving.

---

## 1:45 – 2:55 · Scenario C — the machine that wasn't

**Driver:** Simulation. Select `EQ-0180`. **Confirm Run on EQ-0180** on **Hardware fault** → click →
**Dashboard**.

> "Pump set PS-180, up at Trojena Ridge, dewatering unattended. Same symptom exactly — telemetry
> stops, the network reports the device **not connected**. Identical to the first one. Completely
> different cause."

> "This time the signal was strong — **≈ −42 dBm** — and **zero** neighbouring cells failing. The
> network is healthy, so the silence is the machine itself.
>
> Now the models come in. Device failure at **≈99%**, and a second model names the part: the
> **alternator**."

*(Agent: "Hardware fault confirmed. Technician sent." — card WO-0001 appears)*

**Driver:** point at the work-order card — **Component: alternator**, **Part: ALTERNATOR-24V**.

> "That's the difference between a work order that says *go look at it* and one that says *bring an
> `ALTERNATOR-24V`.*
>
> The machine's own GPS went dark with it, so the agent made a second network call — **CAMARA
> Location Retrieval** — for network-verified coordinates. Then it called the *same API again* on the
> technicians' phones, because their phones are on the same network. 'Who is nearest' is answered by
> the network, right now."

**Driver:** point at the journey rows (**km to Coastal Access Depot · loading · km to the machine**),
then the amber note beneath.

> "An alternator isn't in anybody's van — it's on a depot shelf. So the job isn't 'who is closest',
> it's 'who can collect one and still get there first'.
>
> Ziad is nearer the machine, at **≈20 km**. It sent Youssef instead, and the card says why: Ziad would
> arrive **≈41 minutes later** once the part is collected. Closer is not sooner when the part is not in
> the van."

> **Read the card, not these numbers.** Distances and minutes depend on where the crew are standing
> when you fire. Rehearsal: Youssef Nasser sent, 20.4 km to Coastal Access Depot, 20 min loading,
> 60.5 km on, arrives 2h 18m; Ziad Khalifeh nearer at 20.2 km, 41 minutes later.

**Driver:** now go to **Simulation**, select `EQ-0233`, **confirm Run on EQ-0233** on **Leaving the
site**, click. Go straight to **Maintenance** — do not wait for it.

---

## 2:55 – 3:45 · Don't wait for the machine to stop

**Driver:** Maintenance tab (Predictive is the default). Point at **Forecast failures**.

> "Everything so far was reactive: something went quiet, we worked out why. But the best dispatch is
> the one you schedule.
>
> Same fleet, scored continuously — machines that have **not failed**, ranked by how soon the model
> expects them to. Expected in 24 hours, 48, 72. Vibration and oil particles — the signals that moved."

**Driver:** go to **Assets**, click the top machine's ID (rehearsal: `EQ-0248`). Point at **Detail**.

> "Here's the one I want you to look at. Two badges: **Healthy** — because it is, it's streaming and
> reporting normally. And next to it: **Fails in about 24 hours.**
>
> Both are true at the same time, and that's the entire argument for the model. Vibration up
> **≈1.76**, oil particles up **≈343** — bearing wear and metal in the oil, and those move days ahead.
> Engine temperature — the channel a threshold alarm watches — hasn't moved: **≈79 degrees**.
>
> On held-out machines, two to three days out, our model catches **92.2%** of failures. A temperature
> threshold — what fleets alarm on today — catches **19.6%**. Inside three days; past that we don't
> claim it, and every horizon is in `ml/metrics.json` in the repo."

> On-screen text in rehearsal: *"Healthy right now and still expected to fail. Vibration is up 1.76
> and oil particles up 343, which move days ahead. Engine temperature, the channel a threshold alarm
> watches, has not moved yet."*

---

## 3:45 – 4:20 · The incident that never happens

**Driver:** **Dashboard**. GN-233 should already be outside the dashed perimeter on the west side, and
the **Perimeter** panel is showing.

> "While we were looking at that, one more machine was on the move. Generator GN-233 — nothing wrong
> with it, engine fine, telemetry streaming. It's being moved west, off the site. Maybe a crew is
> repositioning it, maybe it's going somewhere it shouldn't. The system doesn't need to know which.
>
> Keep going west from NEOM and you leave our coverage and pick up another country's network. The
> moment that happens, this machine goes dark and becomes the incident you watched at the start."

**Driver:** point at the Perimeter panel.

> "Except it doesn't. We register the site perimeter with the operator as a **geofence**, and the
> network pushes the crossing to us — no polling, no waiting for silence. Look at what it says:
> **'crossed the site perimeter… Still healthy, still reporting.'** Somebody has been told while
> there's still time to turn it around."

**Driver:** KPI **Incidents prevented: 1**.

> "That's why it's counted separately. A dispatch avoided means we correctly didn't send anyone to a
> silence. This means there *was* no silence."

> If you're early and it hasn't crossed yet, keep talking; it lands within about 35 s of the click.
> Injecting again is refused with a 409.

---

## 4:20 – 4:45 · Proof the network layer is real

**Driver:** switch to the **Render tab** (Simulation, Live CAMARA check). Click **Run live CAMARA
check**. Keep the camera on the panel.

> "That fleet is a simulation of a NEOM-scale site — we can't put thirty machines in the desert this
> week. The network layer is not simulated. This is our public deployment, making live calls to Nokia
> Network as Code right now."

*(the panel fills: host, device, four LIVE blocks)*

> "Device Status — connected, SMS only, roaming in Hungary, because that's where Nokia's sandbox test
> SIM lives. Location Retrieval — Budapest. Congestion Insights on the serving area. And Geofencing
> Subscriptions — a real perimeter watch registered with the operator. Same code path as the fleet,
> one environment variable apart."

> Rehearsal on Render: Reachability 425 ms, Location 172 ms, Congestion High · 22%,
> geofencing `existing · 1`. **Read the latencies on screen**; they have also been over a second.
> The public deployment runs the deterministic agent (the top-bar chip says so). That's deliberate;
> don't point at it, and don't claim the LLM runs there if asked.

---

## 4:45 – 5:05 · The numbers, and how it works

**Driver:** back to the local tab, Dashboard. Point at the KPI bar.

> "Three machines, three identical-looking situations, three different correct decisions: nobody
> sent, the right technician with the right part, and an incident that never happened.
>
> Underneath: an AI agent with the CAMARA APIs registered as **tools it decides when to call** —
> Device Status as the truth layer, Location Retrieval for the machine and the crew, Congestion
> Insights, Geofencing — all through Nokia Network as Code, GSMA Open Gateway, so it's
> carrier-portable rather than locked to one telematics vendor.
>
> Our targets at fleet scale: **40% fewer wasted dispatches, 25% less downtime, 15% off operating
> cost** — and fewer crew-hours driving across the desert in extreme heat."

---

## 5:05 – 5:30 · Close

> "One more thing, and it compounds. Every resolution is recorded against the machine and a
> two-kilometre map cell. Run a site for a fortnight, and repeated coverage incidents in the *same*
> cell promote it to a known dead zone — drawn on the map and handed to the agent as prior evidence
> next time something goes quiet there. A coverage map nobody surveyed for, on a site whose coverage
> changes as it's built.
>
> Every alert validated against network truth before anyone is sent anywhere. NEOM, Red Sea Global,
> Qiddiya, Masdar — anywhere assets outrun coverage.
>
> We're ready to pilot on live fleet data with a regional operator. Thank you."

**Driver:** leave the final frame up — KPI bar with all three outcomes. **Don't point at the map on
the dead-zone line.** A single run won't draw one: a cell is promoted at two coverage incidents
(`KNOWN_DEAD_ZONE = 2`, `backend/app/agent/memory.py`), and this run has one. Narrate the mechanism,
point at nothing.

---

## Recovery playbook

| Symptom | Fix |
|---|---|
| Button hit the wrong machine | The dropdown resets after each injection. Simulation → **Reset fleet**, reset memory with the curl above, start again. |
| "already silent — reset the fleet" | You fired twice on the same machine. Pick another or reset. |
| Nothing seems to happen after a click | You're still on Simulation. Incidents don't switch tabs; go to **Dashboard**. |
| Work-order card vanished | Auto-completed at 90 s. Expected: *"and there's the loop closing — machine back in service."* |
| Perimeter panel not there yet | GN-233 needs ≈35 s. Keep narrating. |
| No machines in Forecast failures | Check `ml_backend: trained` in `/api/debug/health`. The reactive scenarios still work. |
| Work order in the way | The card has **Mark complete**, **No fault found**, **Cancel**. |
| Agent says "known dead zone" in Scenario A | Memory from rehearsal. Reset with `?clear_memory=true`. |
| Trace stalls part-way (LLM mode) | The agent re-asks for the terminal tool; failing that, the rule agent finishes the incident. Let it land. |
| `last_agent_used` is `rule (fallback)` | Groq cap or outage. Swap `LLM_MODEL=groq:qwen/qwen3.8-27b` in `.env`, restart, re-do pre-flight. Only if Groq is down, record in `AGENT_MODE=rule` and don't claim an LLM ran. |
| Render tab shows an error or spins | It's waking. Give it a minute and click again. |
| Dashboard shows "reconnecting…" | Backend died. Restart it (below) and re-do pre-flight. |

**Restarting the backend on Windows** — `pkill` does not match `python.exe -m uvicorn`, so the old
process keeps port 8000:

```bash
netstat -ano | grep ":8000.*LISTENING"
```

```bash
taskkill //PID <PID> //F
```

A venv `python.exe` is a launcher, so one server is two processes; kill both.

---

## Q&A — likely questions

**"Is this really calling Nokia's API, or is it simulated?"**
Both, and the dashboard shows the seam. **Run live CAMARA check** makes real calls to
`network-as-code.p-eu.apihub.nokia.io`: Device Reachability Status v1, Location Retrieval v0,
Congestion Insights and Geofencing Subscriptions, with latency on screen. The *fleet* is simulated,
because the sandbox issues a handful of test SIMs in Hungary; they can't stand in for thirty machines
on a desert site, and live location would route every dispatch to Budapest. Same adapter, same CAMARA
contract, one environment variable apart. **Never claim the fleet is live.**

**"Why didn't you show a machine roaming onto a foreign network?"**
It's on the Simulation tab (**Crossed the border**) and closes as a connectivity ticket with nobody
dispatched. We cut it for time, and the perimeter beat tells the border story better, because it
catches the crossing before the silence.

**"Would this behave the same against the live network, or only against your mock?"**
CAMARA Device Status answers *is this SIM attached* and nothing about radio conditions — no
serving-cell signal, no neighbour-cell failure count. So a fair challenge is: if those numbers
separate a coverage hole from a dead engine, and a real operator never returns them, how does the
blind spot work outside the simulation?

We ask a third API a different question. **Congestion Insights** grades the *serving area* rather
than the device, so it still answers when the device is dark. A machine that goes quiet in a cell the
operator reports as congested is a network failing, not a machine failing; low congestion strengthens
the hardware verdict. Where both exist we prefer radio metrics, because they describe *this device*;
congestion is the fallback, never the override. And in production the radio numbers come from the
device's own last frame before it went dark — radio conditions from the machine; attachment, roaming
and congestion from the operator.

A related detail: a SIM attached for **SMS only** has no data path, so telemetry can't flow even
though it's "connected". The agent treats that as a network cause, not a healthy one.

**"Which part of this is the AI agent, exactly?"**
The orchestration. The agent decides *whether* to call Device Status, *how to weigh* conflicting
signals — unreachable but strong signal is the hard case — *whether* the ML models are relevant, and
*whether* to spend a dispatch. Pydantic AI driving `openai/gpt-oss-120b` on Groq; the CAMARA endpoints
and ML models are tools it chooses to invoke. The wording in the reasoning is the model's own.

**"What stops it dispatching to a machine that's actually fine?"**
Five outcomes, not two. Coverage gap → no dispatch. Roamed onto a foreign network → connectivity
ticket, no dispatch. Reachable with nominal telemetry → transient dropout, no dispatch. Sensor fault →
a low-cost sensor kit that rides in the van. Genuine hardware fault → dispatch with the identified
part. And that's enforced *inside* the terminal tools: each re-derives the verdict from the network
evidence before it will act, so a healthy classification cannot become a work order whatever the
model decides.

**"What if the model gets it wrong on stage?"**
Every terminal action is a tool with fixed logic, so the model chooses *whether* to dispatch, never
*what* a dispatch does — it cannot invent a technician or a part. If it stalls, the deterministic
agent finishes the incident. With `AGENT_MODE=rule` and no model at all: same steps, same evidence,
same verdict, same work order; the phrasing is templated rather than the model's own. The public
Render link runs that mode, so one visitor can't drain the free-tier token budget.

**"How do you know which component failed?"**
A separate classifier over 30 days of per-machine history, trained on four components — hydraulic
pump, cooling system, main bearing, alternator. **88.6%** accuracy, **0.872** macro F1. The component
selects the part, and the part selects the technician.

**"Why did it skip the nearest technician?"**
Because nearest and soonest stop being the same question once parts live in depots. The journey is
technician → depot → machine, and the agent ranks every technician-and-depot pairing by arrival time.
The card says it outright. Depots are deliberately unequal — give every depot one of everything and
the pickup becomes a constant that never changes who goes.

**"What if you're wrong and there's nothing to fix?"**
The technician closes it **No fault found**. The part goes back on the shelf unfitted, crew and
machine return to service, and the dashboard counts it next to the dispatches avoided. It's separate
from **Mark complete** on purpose: a completed repair consumes its part, so closing a wasted trip that
way would invent stock.

**"Where did the training data come from?"**
Synthetic, and the generators are in the repo: `data/dataset_builder.py` (15,000 diagnostic readings)
and `data/history_builder.py` (30 days of per-machine telemetry for forecasting and component models).
In the diagnostic set `NORMAL` and `SENSOR_FAILURE` deliberately overlap, so nothing scores 100% on it.

**"Is the diagnostic step actually machine learning?"**
No, and we don't claim it. Diagnosis is a readable rule (`_predict_rules`). A classifier trained on
the same 15,000 rows agrees with it on **100%** of them, both scoring **95.2%** on held-out assets — so
that's the rule's number. On a call that puts a crew in a truck, a site manager should be able to read
the logic. The ML that earns the name is the forecasting model and the component classifier.

**"Do real machines actually measure vibration and oil particles?"**
Vibration is standard condition monitoring and already arrives as telemetry. Oil is the honest
caveat: on heavy equipment it's mostly *scheduled sampling* with lab turnaround; inline oil-debris
sensors exist but aren't standard fitment. We model both as continuous because the model needs a
multi-day trend, which sampling also gives at lower resolution. Sources in `docs/EVIDENCE.md` §6.

**"Your forecasting AUC is basically 1.0 — isn't that too good?"**
On synthetic data AUC is the wrong number, and we don't lead with it. We report warning time against
the obvious baseline: two to three days out, the model flags **92.2%**, a temperature threshold
**19.6%**. That gap comes from the physics we modelled — vibration and oil lead temperature by days.

**"Why is your baseline engine temperature?"**
Because it's what fleets alarm on today — the incumbent, not the strongest threshold in our data. A
rate-matched **vibration-slope** threshold beats us past 72 hours (**54.2%** at 72–96 h vs our
**7.3%**). Inside 72 hours it catches **70–71%** vs our **92.2–100%**, and alarms on **18 of 24**
never-failing held-out machines vs **0 of 24**. The right production answer is both: slope rule for a
watch-list, model to commit the dispatch. All in `ml/baselines.json`.

**"How do you get 'about 24 hours' from a yes/no classifier?"**
We train the same question at 24, 48 and 72 hours and report the tightest horizon that clears
threshold.

**"Why not just use GPS from the machine?"**
Because the machine is what went silent. If the uplink is down, its GPS is down too. Network-side
location still works, and a compromised device can't spoof it.

**"How is this different from existing fleet telematics?"**
Telematics tells you a machine stopped reporting; it can't tell you *why*, because it only sees the
device side. We add the operator's view of the network as an independent source of truth, through
standardised GSMA Open Gateway APIs rather than vendor lock-in.
