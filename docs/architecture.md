# Architecture

## The problem in one line

When a machine stops sending telemetry, **you cannot tell from the machine why it went
quiet** — because it went quiet. The answer has to come from somewhere else, and the
only system that knows whether the network dropped it is the network.

That is the whole basis of the design, and it is why this is a network-API product
rather than an analytics one.

## Why the network call is irreplaceable

In our fleet data, when an asset stops responding the true cause is split almost
evenly:

| True cause | Share of silent-asset events |
|---|---|
| Hardware failure | 51% |
| Network outage | 49% |

On-board telemetry cannot separate these, because in both cases there is no on-board
telemetry. Roughly half of every "asset went dark" alert is a truck that never needed
to leave the yard — and the only way to know which half you are looking at is to ask
the operator's network directly.

CAMARA **Device Reachability Status** answers that. CAMARA **Location Retrieval**
then answers "where is it?" for a device whose own GPS is dark and therefore cannot
tell you — and answers it again for the crew, whose phones are on the same network,
so "who is nearest" is asked rather than assumed.

### One API is not enough — what Congestion Insights fixes

Reachability tells you the SIM is not attached. It does not tell you *why*, and the
evidence that used to settle it — serving-cell signal strength and neighbour-cell
failure counts — is not something CAMARA Device Status returns. Against the real Nokia
sandbox both fields come back empty, and `nac/nokia.py` leaves them `None` rather than
fabricating a zero. Those two fields were exactly what the coverage-gap verdict rested
on, and in the demo they come from the dataset. So the headline outcome — *the network
dropped it, send nobody* — was a property of the mock and could not have fired against
a live operator.

**CAMARA Congestion Insights** is what makes it real. It grades the **serving area**
rather than the device, which is the whole point: it still answers when the device is
dark. A machine that goes quiet into a cell the operator already reports as congested is
a network failing, not a machine failing; `None`/`Low` congestion clears the network and
sharpens the hardware verdict instead. `Medium` decides nothing and is allowed to decide
nothing.

Two rules keep it honest, both in `agent/tools.py`:

- It is a **fallback, never an override.** Where the radio metrics exist they win,
  because they describe *this device at the moment it went quiet* while congestion only
  ever describes the neighbourhood.
- There is a **50% confidence floor** (`MIN_CONGESTION_CONFIDENCE`). The operator reports
  how sure it is; below half sure that is a guess with a number attached, and acting on
  it is a mistake in both directions — withhold a dispatch on a low-confidence "High" and
  a broken machine sits in the desert, spend one on a low-confidence "Low" and a truck
  rolls for nothing. Under the floor the reading is **reported on the trace and then
  ignored**, and the silence falls through to the fault model as before.

### One API that calls us — Geofencing Subscriptions

Everything above begins with a machine that has already gone quiet. **CAMARA Geofencing
Subscriptions** is how one stops going quiet in the first place, and it is the only
family here that **pushes rather than being polled**: the site perimeter is registered
once with the operator (an 80 km circle around `SITE_CENTER` in `nac/base.py`) and the
network POSTs to our sink the moment a device leaves it. The warning therefore arrives
while the machine is still healthy and still reporting — which on a site kilometres from
Egyptian and Jordanian coverage is the difference between diagnosing a silence and
preventing one. These are counted separately on the dashboard as **Incidents prevented**,
not as avoided dispatches: nothing failed, so there was no dispatch to avoid.

### The four families

| CAMARA family | Endpoint used | What it settles |
|---|---|---|
| Device Status — Reachability | `POST /device-status/device-reachability-status/v1/retrieve` (fallback `/device-status/v0/connectivity`) | is the SIM attached at all? |
| Device Status — Roaming | `POST /device-status/v0/roaming` | attached, but to *whose* network? |
| Congestion Insights | `POST /congestion-insights/v0/query` | how degraded is the serving area, and how sure is the operator? |
| Location Retrieval | `POST /location-retrieval/v0/retrieve` | where is the silent machine — and where is the crew? |
| Geofencing Subscriptions | `POST` / `GET /geofencing-subscriptions/v0.3/subscriptions`, sink `POST /api/nac/geofence-callback` | which machine just left the site? (push) |

Four families, five distinct signals. Reachability, roaming and congestion are issued
together as one network-verify step; Location Retrieval is called twice per dispatch
(asset, then crew); the geofence is one standing subscription that calls us. Every path
above is the one in `backend/app/nac/nokia.py` and is echoed by the dashboard's
live-check panel.

## Layers

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. TELEMETRY                                                        │
│     Per-asset channels: engine temp, signal strength, neighbour-cell │
│     failures, telemetry age, vibration, oil particles, pressure.     │
│     backend/app/simulator/                                           │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ heartbeat stops
┌───────────────────────────▼──────────────────────────────────────────┐
│  2. ANOMALY DETECTION                                                │
│     Heartbeat-freshness monitor opens an Incident and wakes the      │
│     agent. No human in the loop.        backend/app/anomaly/         │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────────┐
│  3. AI AGENT  (Pydantic AI · gpt-oss-120b on Groq)                   │
│     CAMARA endpoints and both ML models are registered as TOOLS the  │
│     agent decides when to call. Recalls what this asset and this map │
│     cell did before. Emits a reasoning trace per step.               │
│     backend/app/agent/  (+ agent/memory.py)                          │
└───┬───────────────────┬───────────────────┬──────────────────────────┘
    │                   │                   │
┌───▼──────────────┐  ┌─▼────────────┐  ┌───▼────────────────┐
│ 4. NETWORK       │  │ 5. ML        │  │ 6. OPERATIONS      │
│ AS CODE          │  │              │  │                    │
│ Reachability     │  │ diagnose:    │  │ work order,        │
│ Status v1        │  │  what broke  │  │ nearest technician │
│ Roaming v0       │  │ forecast:    │  │ carrying the part, │
│ Congestion       │  │  what will   │  │ ETA, routing,      │
│ Insights v0      │  │              │  │ perimeter alerts   │
│ Location         │  │              │  │                    │
│ Retrieval v0     │  │              │  │                    │
│ Geofencing       │  │              │  │                    │
│ Subs v0.3 (push) │  │              │  │                    │
│ app/nac/         │  │ app/ml/      │  │ app/agent/tools.py │
└──────────────────┘  └──────────────┘  └────────────────────┘
```

Geofencing runs alongside the loop rather than inside it: the subscription is registered
with the operator and its events arrive unprompted at `/api/nac/geofence-callback`,
raising a perimeter alert without an incident ever being opened.

## The decision the agent actually makes

`NOT_CONNECTED` is ambiguous on its own — it is what a dead engine and a coverage
hole both look like. The agent resolves it from signals the device cannot provide:

Rows are evaluated in this order (`assess_silence`, `agent/tools.py`):

| Observation | Reading | Action |
|---|---|---|
| Reachable, **roaming on a foreign network** (country ≠ `SA`) | crossed the site boundary onto another operator; its telemetry APN no longer reaches us | connectivity ticket, **no dispatch** |
| Reachable on our own network | connectivity is ruled out, so the silence is on the machine | hand to the fault classifier |
| Unreachable, weak serving cell (≤ −105 dBm), neighbour cells also failing | coverage gap | re-check scheduled, operator notified, **no dispatch** |
| Unreachable, **strong** serving cell, no neighbour failures | the network is fine here, so the machine died | the fault classifier runs → dispatch |
| Unreachable, **no radio metrics**, operator reports **High** area congestion | the device went quiet into a network already struggling here — coverage failure | re-check, **no dispatch** |
| Unreachable, **no radio metrics**, operator reports **None/Low** congestion | the area is healthy, so the silence is the equipment | the fault classifier runs → dispatch |
| Unreachable, congestion **Medium** | decides nothing, and is not made to | hand to the fault classifier |
| Congestion reading below **50% confidence** | too weak to count either way | stated on the trace, then **ignored** — hand to the fault classifier |
| Anything else | ambiguous; a wasted check beats a missed breakdown | hand to the fault classifier |

Three rows carry the weight. *Unreachable but with a healthy radio link* is the case a
naive reachability check gets exactly backwards. *Reachable but roaming* is invisible
without a second API — the device is fine and attached, just not to us. And the
congestion rows are the ones that survive contact with a real operator, because the two
radio-metric rows above them are answered by the dataset and would be answered by
nothing at all on a live network.

### What the silence resolves to

The network verdict is not the end of it — a dispatch-eligible silence still goes to the
fault model, which can overturn it. Five outcomes, and they are graded rather than
switched on and off:

| Outcome | Incident status | Who goes |
|---|---|---|
| Coverage gap (from the radio metrics, congestion, or the model returning `NETWORK_OUTAGE`) | `network_blindspot` | nobody — re-check queued, operator notified |
| Roaming onto a foreign network | `roaming_blocked` | nobody — connectivity ticket, 30-min re-check |
| Model finds every channel nominal | `no_fault` | nobody — transient dropout, telemetry resumed |
| `SENSOR_FAILURE` | `sensor_confirmed` | a technician with a `TELEMETRY-SENSOR-KIT` — cheap, and the machine is fine |
| `DEVICE_FAILURE` | `hardware_confirmed` | a mechanic with the component-specific part the component model named |

The first three are counted as false dispatches avoided; the last two go through CAMARA
Location Retrieval — once for the asset, once for the crew — before a work order exists.

The agent also remembers. Each resolution is recorded against the machine and the ~2 km
map cell it happened in (`agent/memory.py`, `CELL = 0.02°`), so a patch of ground that
has swallowed signal before is treated as evidence rather than coincidence: at two or
more connectivity incidents a cell becomes a **known dead zone**, which the agent opens
its next investigation there by saying out loud, and which is drawn on the operator's map
— a coverage map nobody had to survey for. Memory is structured rather than semantic —
the question is "same asset or same cell, what happened last time?", which has an exact
answer — and it survives a fleet reset, because the fleet is state and the terrain is
knowledge (`POST /api/scenarios/reset?clear_memory=true` for a genuinely blank slate).

## Where ML earns its place

Not in diagnosis, and the concession is sharper than "a threshold would do". The
hand-written rule in `_predict_rules` (`backend/app/ml/client.py`) and the trained
`ml/model.pkl` agree on **100% of all 15,000 rows** — zero disagreements — and score an
identical **95.17%** against the held-out assets. The trained model is not adding
anything the rule does not already have; it is a *check* that the rule still matches the
data. We run the rule, because the decision it gates puts a crew in a truck and a site
manager should be able to read the logic and argue with it. Nothing here is a black box
because on this question nothing needs to be.

It earns its place in **forecasting**, because the signals that matter arrive in
physical order. Bearing wear lifts vibration and oil-particle count days out; seals
let hydraulic pressure sag next; engine temperature — the channel conventional threshold
alarms actually watch — moves in the final hours.

| Hours before failure | This model | Engine-temp threshold |
|---|---|---|
| 0–24 h | 100% | 31.4% |
| 24–48 h | **100%** | 19.9% |
| 48–72 h | **92.2%** | 19.6% |
| 72–96 h | 7.3% | 13.3% |
| 96–120 h | 0% | 4.4% |

Read the whole table, including the bottom two rows where we lose. The models are
trained at 24/48/72 h (`HORIZON_H = 72` in `ml/train.py`) against a 120-hour
degradation ramp, so nothing was fitted to warn earlier than three days and past that
the threshold is the better of two bad options. Inside the window it was built for,
the model gives usable warning where the threshold gives roughly one alarm in five.
Every figure here is `ml/metrics.json`, which is committed — check it.

That baseline is **engine temperature specifically** — the channel fleets alarm on today,
not the best threshold in our own data. The best is a rate-matched threshold on
**vibration slope**, feature 4 of the 26 the model already receives, and past 72 hours it
beats us: **54.2% at 72–96 h against our 7.3%**, median lead **102 h against our 72 h**.
The cost is the window where dispatch is actually decided — inside 72 hours it catches
**70–71%** against the model's **92.2–100%**, it alarms on **18 of 24** never-failing
held-out machines against the model's **0 of 24**, and **90.0%** of its firings land in a
real degradation ramp against **100%**. Earlier and much noisier. A real fleet would run
both: the slope rule for a watch-list, the model to commit a truck. Every figure in this
paragraph is `ml/baselines.json`, written by `ml/baselines.py`, which measures the
committed model on the same by-asset split.

Horizon comes from asking the same question at 24 / 48 / 72 h and reporting the
tightest one the model clears — never from the label.

## Failure behaviour

Every layer degrades rather than breaks, because a demo and a construction site have
that requirement in common.

| If this fails | What happens |
|---|---|
| Nokia sandbox unreachable | per-call fallback to dataset-backed CAMARA, identical contract |
| Reachability Status v1 errors | falls back to `/device-status/v0/connectivity` for the same answer |
| Roaming or Congestion lookup errors | best-effort: logged, fields left empty, the primary reachability answer stands |
| Congestion returned below 50% confidence | reported on the trace and then ignored; the silence falls through to the fault model |
| No radio metrics *and* no congestion reading | treated as ambiguous and investigated as a possible fault — a wasted check beats a missed breakdown |
| Geofence subscription rejected from localhost | the operator will only accept a sink it can reach; the panel says "needs public url" rather than showing a raw 400 |
| LLM stalls without deciding | agent re-asks for the terminal call, then the deterministic agent finishes the incident |
| No model files present | transparent rule-based classifier with the same interface |
| Model returns `NORMAL` | dispatch is refused inside the tool — a healthy reading can never become a work order |
| Model returns `NETWORK_OUTAGE` on a dispatch-eligible silence | refused too: there is no part to carry to a coverage gap, so it resolves as a blind spot |
| Fleet reset mid-investigation | in-flight work is cancelled and abandoned, never written to the fresh state |
| Fleet reset with geofencing armed | perimeter edge-state is cleared, so the next crossing is still read as a crossing |

## Honest boundaries

- The **fleet is simulated.** The Nokia sandbox issues a handful of test SIMs
  provisioned in Hungary; they cannot stand in for thirty machines across a NEOM
  site, and a live location lookup would route every dispatch to Budapest. The
  dashboard's live-CAMARA panel makes real calls and says exactly this on screen.
- The **geofence subscription is real; the crossings are not.** `create_geofence_subscription`
  registers a genuine `area-left` watch with the operator and `/api/nac/geofence-callback`
  answers it, but there is no external network that can observe a simulated fleet — so the
  demo's crossings are evaluated against the same perimeter by the mock and delivered on the
  identical contract. Same split as everywhere else here, and we say so on the panel.
- The **datasets are synthetic**, generated by `data/dataset_builder.py` and
  `data/history_builder.py`, both in the repo. Figures computed from them describe
  the model's behaviour, not evidence about the world.
- State is **in-memory**: a restart resets the fleet. Deliberate for a demo, and the
  first thing a pilot would replace.
