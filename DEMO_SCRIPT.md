# Live Demo Script — FILO Asset Sentinel

Phase 2 demo, MENA Open Gateway Hackathon. **Target: 6:00.** Two people: a **driver** (laptop) and a
**narrator** (speaks). Never the same person.

Four things to land, in this order: **we don't send trucks we don't need to** (blind spot), **silence
has more than one innocent cause** (roaming), **when we do send someone it's right first time**
(hardware + component + the right part), and **we see failures coming days out** (predictive). The
live CAMARA panel is the proof that the network layer is real, held for the end or for Q&A.

Numbers marked ≈ vary per run — **read what's on screen, don't recite from memory.**

> **Re-verify before recording.** This script was last walked end to end against a build that
> predates the current `main`, and the quoted resolution lines came from that run. A great deal
> has changed since. Do a full dry run, confirm every quoted line still matches what the screen
> says, and only then re-stamp this note with the commit you actually rehearsed against.

---

## Locked decisions

| | |
|---|---|
| **Scenario order** | Blind spot **first** (counter-intuitive win), roaming **second** (the cause nobody thinks of), hardware **third** (the payoff). |
| **Reset between scenarios?** | **No.** Running all three without a reset leaves the KPI bar reading *2 false dispatches avoided · 1 dispatch issued* — the entire pitch in one frame. Reset only *before* you start. |
| **Scenario A asset** | `EQ-0295` — Haul Truck HT-295, Red Sea Global, Coastal Access Road |
| **Scenario B asset** | `EQ-0051` — roaming. Any healthy asset works; the mock synthesises the foreign network. |
| **Scenario C asset** | `EQ-0180` — Loader LD-180, NEOM, Trojena Ridge |
| **Scenario D asset** | `EQ-0233` — Excavator EX-233, Red Sea Global — Coastal Access Road. **Use this one and no other.** Crossing time is a property of where the machine starts, and across the current fleet it ranges from 10 s (`EQ-0097`) to 58 s (`EQ-0274`). `EQ-0233` starts 4.6 km from the site centre and crosses at **34 s**, every time — it was the same in 400 simulated runs, because the drift step dwarfs the random walk. It also starts nearest the middle of the map, so it visibly drives the whole way out — and the forecasting model scores it **not at risk**, so it carries no amber ring and "nothing is wrong with this one" is true on both counts. |
| **Modes** | See Pre-flight. Decide `NAC_MODE` / `AGENT_MODE` before you walk in, not on stage. |
| **Model** | `groq:openai/gpt-oss-120b`. `groq:qwen/qwen3.8-27b` also verified end to end if Groq degrades one of them. |

Why those assets: a **haul truck** is mobile, so "it drove into a dead zone" is intuitive. A **loader**
sits and works, so "it didn't go anywhere, it broke" is equally intuitive. The contrast does narrative
work for you.

> ### ⚠️ Groq has a 200,000 token-per-day cap on the free tier
>
> This is the single most likely thing to break your demo, and it fails *quietly*. On 2026-09-03 a
> handful of rehearsal runs put us at **199,781 / 200,000 tokens used**, after which every
> investigation fell back to the rule agent with `last_agent_used: "rule (fallback)"`. The output on
> screen is identical and correct — you would not notice, and you would claim an LLM ran when it
> didn't.
>
> **Check `last_agent_used` in `/api/debug/health` immediately before you present.** If it says
> `rule (fallback)`, either wait out the window or present in `rule` mode honestly. Budget roughly
> 5–8k tokens per investigation: about a dozen full rehearsal runs is your daily ceiling.

---

## Pre-flight (T-10 min, before you're on stage)

```bash
pwsh scripts/dev.ps1
```

- [ ] `curl http://127.0.0.1:8000/api/debug/health` returns your intended modes and
      `"ml_backend": "trained"`. If it says `rule-based`, run `python ml/train.py`.
- [ ] `"live_camara_available": true` in that same response, or the live-proof panel will error
- [ ] **`"last_agent_used"` is `llm`, not `rule (fallback)`** — see the Groq warning above
- [ ] **Predictive maintenance** panel shows at-risk machines (not "unavailable"), and the map is
      showing **dashed amber rings** — that is the same forecast drawn in two places, and the
      click-through in the 3:35 beat depends on it
- [ ] Note which machine is top of the panel and what its **horizon** reads (`< 1 DAY` etc.) — you
      will name it on stage, and it is scored from replayed history so it does not change between
      rehearsal and performance unless you change `FORECAST_AS_OF`
- [ ] **Run `python scripts/scenario_smoke.py` once on the venue network.** In `llm` mode it fails
      loudly if the model never actually ran — a silent fallback produces *identical, correct*
      output, so this is the only way to know the model is live before you claim it is.
- [ ] Dashboard open, browser zoomed so the **three columns** all fit
- [ ] **Reset with memory cleared**, or the agent will recall dead zones it learned in rehearsal
      and Scenario A will open with "I've seen this before" — true, but it pre-empts your beat:

```bash
curl -X POST "http://127.0.0.1:8000/api/scenarios/reset?clear_memory=true"
```

- [ ] KPI bar reads `100.0%` / `30/30` / all zeros — including **Incidents prevented**
- [ ] The **site perimeter** ring is drawn on the map. The geofence beat is meaningless without a
      visible boundary, and every asset starts inside it (furthest is 73.8 km of an 80 km radius)
- [ ] `EQ-0295` selected in the dropdown, ready for the first click
- [ ] Notifications off, Do Not Disturb on, Slack and mail closed

> The scenario buttons print their target asset ID underneath them. **Check the button says the asset
> you mean before every click** — the dropdown resets to the first healthy asset after each injection.

### Two things that move on their own while you talk

- **Work orders auto-complete after 90 seconds** (`WORK_ORDER_COMPLETE_SECONDS`). The machine turns
  green, the technician returns to the pool, and the card greys out — possibly mid-sentence. Rehearse
  with it. You can also close a job deliberately: the card has **Mark complete** and **Delete**.
- **Technicians drift across the map** every tick, because crews drive between jobs. That's the point
  of locating them over the network, and it's worth pointing at.

---

## 0:00 – 0:30 · The problem

> "A giga-project like NEOM runs hundreds of machines across thousands of square kilometres. When one
> of them stops sending telemetry, the site manager has no idea why. Did it break down? Did the sensor
> die? Did it drive into a cellular dead zone?
>
> Here's the trap: the data that would tell you is the data that just stopped arriving. You cannot
> diagnose a silent machine from the machine.
>
> So today the answer is: send someone and find out. A two-hour drive across the desert to *maybe*
> stand next to a perfectly healthy excavator that simply lost signal."

**Driver:** dashboard on screen, nothing clicked yet.

---

## 0:30 – 0:55 · What you're looking at

> "Our operations dashboard. Thirty machines on a live site streaming telemetry — engine temperature,
> signal strength, telemetry age and neighbouring-cell failures. Everything green, fleet availability
> 100%.
>
> The triangles are field technicians. Watch them: they move, because crews drive between jobs. That
> matters later. And the dashed rings are machines the forecasting model expects to fail — we'll come
> back to those.
>
> Now watch what happens when a machine goes dark."

**Driver:** point at the map, the drifting technician markers, then the KPI bar. Don't click yet.

> **Don't say "vibration" here.** Those four are the channels the Asset telemetry panel actually
> draws — `TelemetrySample` carries nothing else. Vibration and oil particles are real, but they live
> in the replayed 30-day history behind the forecasting model, and they appear on screen exactly once:
> in the at-risk line at 3:35. Naming them at 0:30 invites someone to look for a vibration trace that
> isn't there, and it spends the surprise the predictive beat is built on.

---

## 0:55 – 1:45 · Scenario A — the machine that was fine

**Driver:** confirm the buttons read `EQ-0295` → click **Cellular blind spot**.

> "Haul truck HT-295, out on the Red Sea coastal access road. Telemetry just stopped."

*(≈2 s — the asset turns red, an incident opens.)*

> "Nobody touched anything. The agent has opened an incident and it's doing what a site manager
> can't do from an office: asking the **network** whether the truck is reachable — a CAMARA Device
> Reachability Status call through Nokia Network as Code."

**Driver:** trace the reasoning panel with the cursor as steps appear.

> "And here's the interesting part. The device comes back **not connected** — which normally reads as
> 'send a mechanic'. But the agent doesn't stop there. Last serving-cell signal: **≈ −128 dBm**.
> Neighbouring cells failing at the same time.
>
> That is not a broken machine. That is a hole in the coverage."

*(incident closes — BLIND SPOT · NO DISPATCH)*

> "So it logs a cellular blind spot, schedules an automatic re-check, notifies the operator — **and
> dispatches nobody.**"

**Driver:** point at **Work orders — "None issued"**, then the KPI **False dispatches avoided: 1**.

> "That's the field trip that never needed to happen."

---

## 1:45 – 2:20 · Scenario B — the cause nobody thinks of

> **CUT THIS FIRST if you're running long.** The geofence beat at 4:20 now tells the border story
> better — it *prevents* the crossing rather than explaining it afterwards — so this one is the
> cheapest thirty-five seconds to give back. Scenario C is the one that closes the loop; keep that.

**Driver:** select `EQ-0051`. **Confirm the button reads `EQ-0051`.** Click **Crossed the border
(roaming)**.

> "Different machine, same symptom — telemetry stops. But this time the network says something
> stranger: the device is **reachable**. It's alive, it's attached, it's just not attached to *us*.
>
> NEOM sits at the head of the Gulf of Aqaba, kilometres from Egyptian and Jordanian networks. This
> machine worked its way along the site boundary and handed off to a **Jordanian** operator. It's
> perfectly healthy — its telemetry APN simply doesn't route back to us any more."

*(incident closes — ROAMING · NO DISPATCH)*

> "No on-board sensor can see this. Nothing on the machine is wrong. Only the operator's own view of
> the network reveals it — and the correct response is a connectivity ticket, not a mechanic.
>
> Two machines now, two silences, two completely different innocent causes. Neither one got a truck."

**Driver:** KPI now reads **False dispatches avoided: 2**.

---

## 2:20 – 3:35 · Scenario C — the machine that wasn't

**Driver:** select `EQ-0180`. **Confirm the buttons read `EQ-0180`.** Click **Hardware fault**.

> "Loader LD-180, up at Trojena Ridge. Same symptom exactly — telemetry stops, network reports the
> device **not connected**. Identical to Scenario A. Completely different cause."

*(watch the trace)*

> "Look at the signal this time: strong, and **zero** neighbouring cell failures. The network here is
> healthy — so the silence is the machine itself.
>
> Now the ML model comes in. And it doesn't just say 'something broke' — it names the part. Thirty
> days of this machine's own history: **battery voltage sagging, alternator output falling away.**
> Device failure at **≈99% confidence**, and the failing component is the **alternator**."

**Driver:** point at the work-order card — **Component** and **Part** rows.

> "That's the difference between a work order that says *go look at it* and one that says *bring an
> `ALTERNATOR-24V`.*"

**Driver:** as the location step lands, point at the map — the dispatch line draws itself.

> "The on-board GPS is dark, so the agent makes its second network call: **CAMARA Location Retrieval**
> — network-verified coordinates straight from the operator, for a device that cannot report its own
> position.
>
> Then it does something I want to highlight. It calls the *same API again* — on the technicians'
> phones. Because their phones are devices on the same network. So 'who is nearest' is answered by the
> network, right now, not by a roster written this morning."

**Driver:** point at the **route line** on the work-order card — the three legs — then at the
**"nearer but later"** note beneath it.

> "An alternator is a pallet item. It is not in anybody's van, it is on a shelf at a depot — so the
> job isn't 'who is closest', it's 'who can pick one up and still get there first'.
>
> Look at what it worked out. Ziad Khalifeh is **≈19 km** from the machine, the nearest man we have.
> It sent Youssef Nasser instead, and the card says why: Ziad would arrive **≈44 minutes later**,
> because the only depot holding an alternator is the other way.
>
> Closer is not sooner once the part is somewhere else. On a map that dispatch looks like a bug, so
> the card explains itself in the same breath."

*(≈28 s from dark to dispatched)*

> "Under thirty seconds, from telemetry going dark to the right technician, routed through the depot
> that actually has the part. No human in the loop at any point."

> **Read the card, not these numbers.** The two distances and the minutes-later figure are computed
> from where the crew happen to be standing when you fire it, and the crew drift between jobs. The
> shape is what is fixed: the nearest technician is not the one sent, and the card gives the reason
> in minutes. On the current fleet it has been **Ziad nearest at ≈19 km, Youssef sent, ≈44 minutes
> later** on every rehearsal run.

**Driver (optional):** click **Mark complete** on the card.

> "And when the repair is done, the loop closes — technician back in the pool, machine back in
> service."

---

## 3:35 – 4:20 · Don't wait for the machine to stop

**Driver:** point at the **Predictive maintenance** panel, then at the **dashed amber rings** on the
map.

> "Everything so far was reactive: something went quiet, we worked out why. But the best dispatch is
> the one you schedule.
>
> Same fleet, scored continuously — machines that have **not failed**, ranked by how soon the model
> thinks they will. Every one of them is ringed on the map. Those machines are running right now.
> Nothing is wrong with them today."

**Driver:** click the top row of the panel — the machine with **< 1 DAY**. Watch it select on the
map, then move the cursor to the **Asset telemetry** panel bottom-left.

> "Here's the one I want you to look at."

*(the machine is ringed and selected; the telemetry panel fills in)*

> "Two badges. It says **healthy** — because it is. It's streaming, every live channel is inside its
> normal band, and no alarm on any conventional system is going off. And next to it: **at risk, about
> twenty-four hours.**
>
> Both of those are true at the same time, and that is the entire argument for the model.
>
> Look at why it thinks so: **vibration up 1.76, oil particles up 343.** That's bearing wear and metal
> in the oil. Those move **days** ahead. Engine temperature — the one signal a threshold alarm
> actually watches — is still 71 degrees. Completely normal. It won't move until the last few hours,
> and by then you're not scheduling a repair, you're recovering from a breakdown.
>
> On held-out machines, two to three days out: our model catches **92.2%** of failures. A temperature
> threshold — what fleets actually alarm on today — catches **19.6%**.
>
> Inside three days. Past that we lose — nothing was trained to warn earlier, and the numbers for
> every horizon are in `ml/metrics.json`, which is in the repo."

> **Read what's on screen, not these numbers.** Vibration, particle counts and the horizon differ per
> machine and per run. The shape of the story is what's fixed: healthy *and* at risk, with the two
> leading channels moved and engine temperature flat.

---

## 4:20 – 4:55 · The incident that never happens

> **Stagecraft:** click this button *during* the predictive beat above, then narrate predictive while
> the machine drives — you do not want to stand and watch it. `EQ-0233` takes **34 s** to reach the
> perimeter, so click it about **fifteen seconds into predictive** (≈3:50) and it crosses at ≈4:24,
> a few seconds into this beat, with the audience watching. Click at the *top* of predictive and it
> crosses at ≈4:09 — still fine, but it will already be sitting outside when you get here, so drop
> "watch it" and narrate the aftermath instead.
>
> Use `EQ-0233` and no other. Crossing time is set by where the machine starts, and on the current
> fleet it ranges from 10 s (`EQ-0097` — gone before you finish the sentence) to 58 s (`EQ-0274` —
> long after you've moved on). See Scenario D in Locked decisions.

**Driver:** select `EQ-0233`, **confirm the button reads `EQ-0233`**, click **Leaving the site
(geofence)**. Come back to the map now — it should be out near the western edge, or crossing.

> "One last machine. Nothing is wrong with this one — watch it. Engine fine, telemetry streaming,
> every channel nominal. It's just driving west.
>
> NEOM is on the Gulf of Aqaba. Keep going west and you leave our coverage and pick up an Egyptian
> network — and the moment that happens, this machine goes dark and becomes the incident you saw me
> investigate four minutes ago."

*(the asset crosses the perimeter; a blue alert appears)*

> "Except it doesn't. We registered the site perimeter with the operator as a **geofence**, and the
> network told us the moment it crossed — no polling, no waiting for silence.
>
> Look at what the alert says: **perimeter, no fault.** The machine is still healthy, still
> reporting. It hasn't broken and it hasn't gone quiet. Somebody has been told while there's still
> time to turn it around, or hand it to the connectivity team before it drops off.
>
> Everything else I've shown you explains a silence after it happens. This one means the silence
> never happens."

**Driver:** point at the KPI **Incidents prevented: 1** — a separate counter from false dispatches
avoided.

> "And that's why it's counted separately. An avoided dispatch means we correctly decided not to send
> anyone to a failure. This means there *was* no failure."

---

## 4:55 – 5:15 · Proof the network layer is real

**Driver:** if the **Network as Code** panel is minimised, click **+** to open it, then click **Run
live CAMARA check**.

> "One last thing. That fleet is a simulation of a NEOM-scale site — we can't put thirty machines in
> the desert this week. But the network layer is not simulated."

*(the panel fills in — real host, real device, latencies)*

> "That's a live call to Nokia Network as Code, right now. Device Reachability Status and Location
> Retrieval, round trip in under a second. The sandbox test SIM is provisioned in Hungary, which is
> why it reports Budapest — so the fleet above runs on replayed telemetry through the identical CAMARA
> contract. Same code path, one environment variable apart."

---

## 5:15 – 5:35 · The numbers, and how it works

**Driver:** point at the KPI bar — **2 false dispatches avoided · 1 dispatch issued**.

> "Three machines, three identical symptoms, three different correct decisions. That's the whole
> product.
>
> Underneath: an AI agent with the CAMARA APIs registered as **tools it decides when to call** — not
> buttons a person presses. Device Reachability Status is the truth layer. Location Retrieval is the
> dispatch layer, used twice — the machine and the crew. Both through Nokia Network as Code, GSMA Open
> Gateway compliant, so it's carrier-portable rather than locked to one telematics vendor.
>
> Our targets at fleet scale: **40% fewer wasted dispatches, 25% less downtime, 15% off operating
> cost** — and measurably fewer crew-hours driving across the desert in extreme heat."

---

## 5:35 – 5:55 · Close

> "One more thing, and it's the thing that compounds. Every resolution you just watched was recorded
> against the machine and against a two-kilometre map cell. Six minutes isn't long enough to show you
> what that buys — you've watched two connectivity incidents, and they were in two different cells. But
> run this site for a fortnight and the second and third silence in the *same* cell come back coverage,
> and that cell is promoted to a known dead zone: drawn on the map, and handed to the agent as prior
> evidence the next time something goes quiet there.
>
> That is a coverage map nobody surveyed for. A construction site's coverage changes as the site is
> built, so this learns the terrain instead of re-deriving it every time.
>
> Every alert validated against network truth before anyone is sent anywhere. It scales across NEOM,
> Red Sea Global, Qiddiya, Masdar — anywhere assets outrun coverage.
>
> We're ready to pilot on live fleet data with a regional operator. Thank you."

**Driver:** leave the final frame up — all three incidents in the feed, KPI bar showing both outcomes.
**Do not gesture at the map on this line.** There will be no dead zone drawn on it, and pointing at
an empty map is the one moment in six minutes where the audience sees a claim fail.

> **Why there won't be one.** A cell is promoted at two coverage incidents (`KNOWN_DEAD_ZONE = 2` in
> `backend/app/agent/memory.py`), and the current 30-machine fleet occupies **30 distinct 2 km cells**
> — no two machines share one. So a zone needs the *same* machine to produce two coverage incidents,
> which needs a fleet reset in between, which is not in this run. That is the honest state of it: the
> mechanism is real and the map draws it (`FleetMap.tsx` renders the cells and a legend), but a clean
> six-minute demo cannot manufacture the evidence for it, and lowering the threshold to make one
> appear on stage would be staging the evidence rather than showing it. Narrate the mechanism, promise
> the fortnight, point at nothing.
>
> If a judge asks to *see* one: reset **without** `clear_memory` (memory deliberately outlives the
> fleet, which is the point), then re-fire the blind spot on the same machine. Two coverage incidents
> in one cell, and the zone draws. Caveat worth knowing before you offer it: the machine random-walks
> between reset and injection, and `EQ-0295` sits only ~0.34 km from a cell edge, so the second
> incident occasionally lands in the neighbouring cell and no zone appears. Say what you're doing
> while you do it, and if it lands next door, that is a two-kilometre grid behaving exactly as
> described — not a failure. It just isn't a thing to point at mid-close.

---

## Recovery playbook

| Symptom | Fix |
|---|---|
| Scenario button does nothing | Check the button's target ID. If the dropdown is empty, click **Reset fleet**. |
| "already silent — reset the fleet" | You fired twice on the same machine. Deliberate — the second injection is refused so it can't contradict the first. Pick another asset or reset. |
| Reset clicked mid-investigation | Safe. Anything in flight is abandoned rather than landing on the fresh fleet. |
| Machine turns green mid-narration | The work order auto-completed at 90 s. Expected. Say *"and there's the loop closing — machine back in service."* |
| Clicking a machine seems not to select | A brand-new incident takes the view once, by design, so the trace follows a machine going dark. Click again once the trace has landed. |
| Geofenced machine hasn't crossed yet | `EQ-0233` needs 34 s of driving. Keep narrating; it crosses on its own. Injecting again is refused with a 409. If you fired on a different machine it could be anywhere from 10 s to 58 s out — narrate predictive until the blue alert lands, and don't promise a time you didn't measure. |
| No dashed rings on the map | The forecast fetch failed or the model is untrained. Check `ml_backend` is `trained` in `/api/debug/health`; the reactive scenarios still work without it. |
| Work order in the way | **Delete** on the card removes it and releases the technician. **Mark complete** closes it properly. |
| Agent says "known dead zone" in Scenario A | Rehearsal memory. True and defensible — lean into it, or reset with `?clear_memory=true`. |
| Trace stalls part-way (LLM mode) | It self-corrects: the agent re-asks for the terminal tool call, and failing that the rule agent finishes the incident. Say nothing and let it land. |
| LLM slow, rate-limited, or daily cap hit | **First** swap the model: `LLM_MODEL=groq:qwen/qwen3.8-27b` in `.env`, restart backend. Same trace, same pacing, narration unchanged. **Only if Groq itself is down**, say *"switching to our deterministic path"* and set `AGENT_MODE=rule`: same content on screen, but it finishes in ~5 s instead of ~28 s, so the trace lands before your narration does — cut to the result and talk over the finished panel, don't pace it like the LLM run. |
| Dashboard shows "reconnecting…" | Backend died. Restart it (below); the dashboard reconnects on its own. |
| KPIs/state look stale or wrong | **Reset demo**, re-run from Scenario A. |
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
Both, and the dashboard shows the seam. Hit **Run live CAMARA check** — that is a real call to
`network-as-code.p-eu.apihub.nokia.io`, Device Reachability Status v1 and Location Retrieval v0, with
the latency on screen. The *fleet* is simulated, because the sandbox issues a handful of test SIMs
that sit in Hungary and always report reachable; they can't stand in for thirty machines across a
desert site, and a live location lookup would route every dispatch to Budapest. Same adapter, same
CAMARA contract, one environment variable apart. **Never claim the fleet is live.**

**"Would this behave the same against the live network, or only against your mock?"**
Yes, and the reason is worth giving in full, because the obvious objection is a good one.

CAMARA Device Status answers *is this SIM attached* and nothing about radio conditions — no
serving-cell signal, no neighbour-cell failure count. So a fair challenge is: if those two numbers
are what separate a coverage hole from a dead engine, and a real operator never returns them, how
does the blind spot work outside your simulation?

It works because we ask a third API a different question. **Congestion Insights** grades the
*serving area* rather than the device — which means it still answers when the device is dark. A
machine that goes quiet into a cell the operator already reports as congested is a network
failing, not a machine failing. And the reverse is just as useful: low congestion clears the
network, which makes the hardware verdict stronger rather than weaker. You can watch that call
happen in the **Run live CAMARA check** panel — real level, real confidence, from the sandbox.

Where both sources exist we prefer the radio metrics, because those describe *this device* at the
moment it went silent while congestion only ever describes the neighbourhood. Congestion is the
fallback, never the override — letting a busy cell excuse a broken machine is the expensive
mistake.

Those radio numbers, incidentally, do not need to come from CAMARA at all in production: a device
reports its own signal conditions in the last frame it sends *before* going dark, which is the
same frame our classifier already reads. Radio conditions from the machine, attachment, roaming
and congestion from the operator. That split is the architecture, not a workaround.

**"Which part of this is the AI agent, exactly?"**
The orchestration. The agent decides *whether* to call Device Status, *how to weigh* conflicting
signals — unreachable but strong signal is the hard case — *whether* the ML model is even relevant,
and *whether* to spend a dispatch. Pydantic AI driving `openai/gpt-oss-120b` on Groq; the CAMARA
endpoints and the ML models are registered as tools it chooses to invoke. The wording in the trace is
the model's own, not templated.

**"What stops it dispatching to a machine that's actually fine?"**
Five outcomes, not two. Coverage gap → no dispatch. Roamed onto a foreign network → connectivity
ticket, no dispatch. Reachable with nominal telemetry → transient dropout, re-check, no dispatch.
Sensor fault → a low-cost sensor kit, not a mechanic. Genuine hardware fault → dispatch with the
identified part. Three of the five send nobody at all; the fourth sends a sensor kit instead of a
mechanic. The response is graded to what actually broke, not switched on and off.
And critically, that's enforced *inside* the terminal tools. Every one of them independently
re-derives the verdict from the network evidence before it will act, so a healthy classification
cannot become a work order regardless of what the model decides.

**"What if the model gets it wrong on stage?"**
Two guards. Every terminal action is a tool with fixed logic, so the model chooses *whether* to
dispatch, never *what* a dispatch does — it cannot invent a technician or a part. And if it stalls
without deciding, the deterministic agent finishes the same incident. You can run the whole demo with
`AGENT_MODE=rule` and no model at all: same steps, same evidence, same verdict, same work order. Two
things differ, and neither is content — the phrasing of the reasoning is templated rather than the
model's own, and the whole investigation lands in **~5 s instead of ~28 s**, because nothing is
waiting on a model. That speed changes how you present it: you narrate over a finished panel rather
than alongside a filling one (see the recovery playbook).

**"How do you know which component failed, not just that something did?"**
A separate classifier over 30 days of per-machine history across five channels, trained on four
components with distinct signatures — hydraulic pump, cooling system, main bearing, alternator.
88.6% accuracy, 0.872 macro F1. Alternator faults are the interesting case: they're close to
invisible without battery voltage, which is why that channel is in there. The component is what
selects the part, and the part is what selects the technician.

**"Why did it skip the nearest technician?"**
Because nearest and soonest stopped being the same question once the parts moved into depots. The
four components we name are pallet items — a 40 L/min pump, an XL radiator core — so they sit on a
depot shelf, not in six vans. The journey is technician to depot to machine, and the agent ranks
every technician-and-depot pairing by arrival time. The card states it outright: *"X is nearer the
machine at Y km, but would arrive Z minutes later once the part is collected."*

Worth adding if they press: this is also why the depots are deliberately unequal. Trojena holds no
alternator, so an alternator failure there has to be served from the coast. Give every depot one of
everything and the pickup becomes a constant added to everybody's journey that never changes who
goes — routing theatre. 25% of field service calls need a second visit (Aberdeen); sending somebody
who has to go back for the part is how you become that statistic.

**"What if you're wrong and there's nothing to fix?"**
Then the trip is recorded as what it was. The technician closes it **no fault found**, the component
goes back on the shelf it came from unfitted, the crew and the machine return to service, and the
dashboard counts it next to the dispatches we avoided. It is a separate action from completing the
job on purpose: a completed repair consumes its part and the depot books a replacement in, so
closing a no-fault visit that way would invent a spare out of a wasted journey and drift stock upward
every time the model was wrong. A product sold on cutting wasted trips should show its own.

**"Where did the training data come from?"**
Synthetic, and we'll show you the generators. `data/dataset_builder.py` makes the 15,000 diagnostic
readings; `data/history_builder.py` makes 30 days of continuous per-machine telemetry for the
forecasting and component models. The honest part: in the diagnostic set `NORMAL` and
`SENSOR_FAILURE` deliberately overlap, so nothing scores 100% on it — about half the sensor
faults are genuinely indistinguishable from healthy readings, and we know exactly why. What
*is* separated cleanly is the decision that actually matters: coverage gap versus hardware
failure.

**"Is the diagnostic step actually machine learning?"** — ask this on yourself before a judge does.
No, and we don't claim it. Diagnosis is a rule you can read in a couple of dozen lines
(`_predict_rules`). We trained a classifier on the same 15,000 rows and it agrees with that rule
on **100% of them** — zero disagreements — both scoring the same **95.2%** on held-out assets. So
95.2% is the rule's number, not a model's. We keep the model as a check that the rule still matches
the data, and we run the rule because on a call that puts a crew in a truck in the desert, a site
manager should be able to read the logic and argue with it. The machine learning that earns its
name is the forecasting model and the component classifier — neither has a rule-shaped
alternative, and the component one especially: a threshold returns a yes or a no, never a part
number.

**"Do real machines actually measure vibration and oil particles?"**
Yes, and it is worth answering precisely because the two are not equally routine.

Vibration is standard condition monitoring and already arrives as telemetry — post-2015 Cat and
Komatsu machines broadcast hundreds of CAN-bus points, accelerometers are cheap, and Komatsu sells
vibration analysis as a machine-health service today.

Oil is the honest caveat. On heavy equipment it is predominantly *scheduled sampling*, not a live
feed: a technician draws a sample and Cat's S·O·S lab turns it round in about a day. Inline
oil-debris sensors exist — inductive, capacitive, optical — and are an active field precisely
because lab sampling cannot reflect real-time status, but they are not standard fitment the way
engine data is.

We model both as continuous because what the model needs is a multi-day trend, and sampling gives
you that anyway at lower resolution. On a real fleet today those two channels would arrive at
different cadences and the ingestion layer would carry that. Sources are in `docs/EVIDENCE.md` §6.

**Say this rather than implying everything streams.** It shows you know the domain and not just
the dataset, and the answer is stronger than the hedge.

**"Your forecasting AUC is basically 1.0 — isn't that too good?"**
On synthetic data, yes, AUC is the wrong number to judge us on and we don't lead with it. The number
we report is **warning time against the obvious baseline**: at two to three days out the model flags
92.2% of failures, a temperature threshold flags 19.6%. That gap is a property of the physics we modelled
— vibration and oil-particle trends lead engine temperature by days — not of the classifier being
clever. On real fleet data the absolute numbers move; the ordering of those signals doesn't.

**"Why is your baseline engine temperature? Did you try thresholding anything else?"**
Yes, and this is the answer to volunteer rather than wait for. Temperature is the baseline because
it is what fleets alarm on *today* — it is the incumbent, not the strongest threshold in our data.
The strongest is a rate-matched threshold on **vibration slope**, and past 72 hours it beats us:
**54.2% detection at 72–96 h against our 7.3%**, median lead **102 h against our 72 h**. And that
slope is feature 4 of the 26 the model already receives, so we can't even call it an unfair
comparison — it beat us with something we handed it.

What it costs is the window where you actually decide to send a truck. Inside 72 hours that rule
catches **70–71%** where the model catches **92.2–100%**; it alarms at least once on **18 of the 24
never-failing machines** in the held-out split, against **0 of 24** for the model; and only **90.0%**
of its firings land inside a genuine degradation ramp, against **100%**. It is an earlier and far
noisier smoke detector. The right production answer is both — the slope rule feeds a watch-list, the
model commits the dispatch — and that is the answer to give, not a defence of the model alone.

Every number in those two paragraphs is in `ml/baselines.json`, committed, and regenerated by
`python ml/baselines.py`. If a judge asks where they come from, open the file.

**"How do you get 'about three days' from a yes/no classifier?"**
We don't. We train the same question at 24, 48 and 72 hours and report the tightest horizon that
clears threshold. The estimate comes from the models, never from the label.

**"Why not just use GPS from the machine?"**
Because the machine is the thing that went silent. If the telemetry uplink is down, its GPS is down
too. Network-side location is the only position source that still works — and it can't be spoofed by
a compromised device.

**"Why locate the technicians over the network instead of using their last known position?"**
Because a crew position goes stale the moment someone drives to a job, and dispatching on stale
positions is how you send the second-nearest person. Their phones are devices on the same network, so
the same CAMARA call answers both halves of the question. In live mode we only locate technicians
with their own device mapping — otherwise they'd all collapse onto the shared sandbox SIM and
"nearest" would be meaningless.

**"How is this different from existing fleet telematics?"**
Telematics tells you a machine stopped reporting. It cannot tell you *why*, because it only sees the
device side. We add the operator's own view of the network as a second, independent source of truth
— and that's the signal that separates a dead engine from a dead cell. Our angle isn't that nobody
does asset monitoring; it's that we apply *standardised* operator APIs, through GSMA Open Gateway, to
a problem currently solved with vendor lock-in and manual triage.
