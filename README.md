# FILO Asset Sentinel

**Dynamic IoT Asset Analytics for Giga-Projects** — Team FILO, MENA Open Gateway Hackathon (GSMA MENA Ignite).
Theme 2: *Smart Cities, Urban Safety & Mega-Project Infrastructure*.

When a piece of heavy equipment on a NEOM-scale site stops sending telemetry, nobody knows whether it
**broke down**, its **sensor failed**, or it just **drove into a cellular dead zone**. The default is to
send a field engineer into the desert on a guess — expensive, slow, and often wrong.

FILO Asset Sentinel is an **autonomous diagnostic agent** that settles the question before anyone
drives anywhere:

```
 asset goes silent
   └─▶ CAMARA Device Status + Roaming + Congestion Insights   ── is the network up here?
         ├─ coverage gap    ─▶ log blind spot, re-check, notify operator        ✗ NO DISPATCH
         ├─ roaming abroad  ─▶ connectivity ticket, re-check                    ✗ NO DISPATCH
         └─ network fine    ─▶ fault classifier
                                ├─ nothing wrong ─▶ transient dropout, re-check ✗ NO DISPATCH
                                └─ real fault ─▶ CAMARA Location Retrieval ─▶ work order + nearest
                                                 (asset, then crew)             technician w/ the part

 asset still healthy, but drifting off site
   └─▶ CAMARA Geofencing Subscriptions   ── the network calls us, unprompted     ⚠ INCIDENT PREVENTED
```

Four CAMARA API families, five network signals, and one of them pushes rather than being
polled. Every step of the agent's reasoning is streamed to a live operator dashboard.

---

## Is this a real problem?

Yes, and the industry already has names and budgets for it. A wasted field visit is a
**truck roll** — **$250–$600, up to $1,000** — and **"no fault found"** is the standard
term for the trip where the technician arrives and there is nothing to repair. Vendors put
the NFF rate at **17–20% of all dispatches**; on an operator running 1,000 dispatches a
day that is **$10.7M a year** spent achieving nothing.

On the other side, unplanned downtime on construction equipment runs
**$3,200–$8,700 per machine per day**, and unplanned repairs cost **3–5× more** than
planned ones. Predictive maintenance is established practice: McKinsey puts it at
**18–25% lower maintenance cost** and **up to 50% less unplanned downtime**.

And the machines really are on mobile networks — **73% of construction telematics is
cellular** — on sites where coverage is *"often inconsistent"*. NEOM is being built right
now with STC as its network partner, which is what makes asking the operator possible.

Sources, source-quality caveats, and the claims we deliberately do **not** make:
[docs/EVIDENCE.md](docs/EVIDENCE.md).

## Why the network call is irreplaceable

When an asset stops sending telemetry you cannot work out *why* from the asset — it
stopped sending telemetry. In our fleet data the true cause of a silent-asset event
splits almost evenly:

| True cause | Share of silent-asset events |
|---|---|
| Hardware failure | 51% |
| Network outage | 49% |

Roughly half of every "asset went dark" alert is a truck that never needed to leave
the yard, and **no amount of on-board sensing can tell you which half you are looking
at.** Only the operator's network knows whether it dropped the device. That is what
CAMARA Device Reachability Status provides, and it is the part of this system nothing
else can substitute for.

`NOT_CONNECTED` is still ambiguous on its own — it is what a dead engine and a
coverage hole both look like. The agent resolves it using signals the device cannot
report:

| Observation | Reading | Action |
|---|---|---|
| Reachable · **roaming on a foreign operator** | crossed the border; telemetry can't reach us | connectivity ticket, **no dispatch** |
| Reachable on our own network | connectivity ruled out — it's the machine | classify fault |
| Unreachable · weak cell (≤ −105 dBm) · neighbour cells failing | coverage gap | re-check, **no dispatch** |
| Unreachable · **strong** cell · no neighbour failures | network is fine, so the machine died | classify fault → dispatch |
| Unreachable · no radio metrics · **High** area congestion | went quiet into a network already struggling here | re-check, **no dispatch** |
| Unreachable · no radio metrics · **None/Low** congestion | the area is healthy, so the silence is the equipment | classify fault → dispatch |
| Unreachable · **Medium** congestion, or a reading below 50% confidence | decides nothing, and isn't made to | stated on the trace, then classify fault |

The fourth row is the one a naive reachability check gets exactly backwards. The first
is invisible without the roaming API — the machine is healthy *and attached*, just not
to our network, so nothing on the device can tell you why its data stopped arriving.
NEOM sits within a few kilometres of Egyptian and Jordanian networks, so this is an
ordinary event on that site.

Three of the five outcomes send nobody: a coverage gap, a machine roaming onto a foreign
operator, and a silence the fault model reads as a transient dropout with nothing wrong.
The fourth sends a technician with a cheap `TELEMETRY-SENSOR-KIT` rather than a mechanic,
and only the fifth — a confirmed hardware fault — is worth a truck and the
component-specific spare part. Grading the response to what actually broke, not just
gating dispatch on and off, is the product.

### Why Congestion Insights is load-bearing, not a fourth logo

The two radio-metric rows are the ones the demo's blind-spot outcome rests on — and
CAMARA Device Status returns **neither** signal strength nor neighbour-cell failures.
Against the real sandbox both come back empty; in the demo they come from the dataset.
Left there, the headline "don't send the truck" verdict would have been a property of our
mock, not something that could ever fire against a live operator.

**CAMARA Congestion Insights** grades the *serving area* rather than the device, so it
still answers when the device itself is dark. High congestion where a machine just went
quiet is a network failing, not a machine failing; `None`/`Low` clears the network and
sharpens the hardware verdict instead. It is deliberately a **fallback, never an
override** — where the radio metrics exist they win, because they describe this device at
the moment it went silent while congestion only ever describes the neighbourhood — and
there is a **50% confidence floor** below which the operator's own reading is shown on
the trace and then ignored, because acting on a guess is a mistake in both directions.

### Catching it before it goes quiet — Geofencing Subscriptions

Everything above starts with a machine that has already gone silent. The fourth API
family is how one stops going silent in the first place, and it is the only one that
**pushes**: the site perimeter is registered with the operator as a CAMARA Geofencing
subscription, and the network POSTs to our sink the moment an asset crosses it. No
polling, and the warning lands while the machine is still healthy and still reporting.
On a site kilometres from Egyptian and Jordanian coverage, that is the difference between
diagnosing a silence and preventing one — so the dashboard counts these as **Incidents
prevented**, a separate KPI from false dispatches avoided. Nothing failed; there was no
dispatch to avoid.

Dispatched jobs then complete: the technician returns to the pool and the machine
comes back online, so the fleet heals rather than draining away a crew member per
incident.

### Both ends of the dispatch are network-located

A technician's phone is a device on the same network as the machine, so the same CAMARA
Location Retrieval call answers both halves of the question: *where is the broken asset*,
and *who is genuinely nearest to it*. Crews drive between jobs, so a rostered or
last-known position is stale exactly when it matters — dispatching on one is how you send
the second-nearest person. The agent asks instead, and the work order records whether the
assignment was made against a network-verified position.

### It learns the site

The agent records how each incident resolved against the machine and the patch of
ground it happened on. An area that has swallowed signal before is evidence: the third
time a machine goes quiet in the same cell, the agent opens with *"this is a known dead
zone, not a run of bad luck"* and says so in its verdict, rather than investigating
from scratch and letting nobody notice the pattern. Memory survives a fleet reset —
the fleet is state, what the agent learned about the terrain is knowledge.

Those learned dead zones are drawn on the site map. It is a coverage map nobody had
to survey for: it falls out of the agent doing its job, and it tells the network team
exactly where to look.

Both datasets are synthetic and their generators are in the repo
(`data/dataset_builder.py`, `data/history_builder.py`). Numbers computed from them
describe how the system behaves — they are not evidence about the world, and we do
not present them as such.

## Seeing it coming

First, what the machine learning here is *not*. The diagnosis step — coverage gap vs.
roaming vs. sensor vs. hardware — is a transparent rule you can read in a couple of dozen
lines (`_predict_rules` in `backend/app/ml/client.py`). We also trained a gradient-boosted
classifier on the same 15,000 rows, and it agrees with that rule on **100% of them** —
zero disagreements, on every row and on the held-out split, where both score the same
**95.2%**. So that 95.2% is not evidence of a model doing anything: it is the rule's
number. The model is a *check* that the rule still matches the data, not a black box
standing in front of a decision that puts people in trucks in the desert — and on that
particular call we would rather ship something a site manager can read and argue with.
The real ML is below, and no rule reproduces it.

Diagnosis is only half of it. `data/telemetry_history.csv` (from `data/history_builder.py`) is 30 days
of continuous per-machine telemetry with a physically ordered degradation ramp: bearing wear lifts
**vibration** and **oil-particle count** first, seals let **hydraulic pressure** sag next, and
**engine temperature** — the signal conventional threshold alarms actually watch — only spikes in the final hours.

So the forecasting model is scored on warning time, not accuracy:

| hours before failure | this model | engine-temp threshold |
|---|---|---|
| 0–24 h | 100% | 31.4% |
| 24–48 h | **100%** | 19.9% |
| 48–72 h | **93.8%** | 19.6% |
| 72–96 h | 7.3% | 13.2% |
| 96–120 h | 0% | 4.3% |

Read the whole table, including the bottom two rows where we lose. The models are
trained at 24/48/72 h (`HORIZON_H = 72` in `ml/train.py`) against a 120-hour
degradation ramp, so nothing was fitted to warn earlier than three days and past that
the threshold is the better of two bad options. Inside the window it was built for,
the model gives usable warning where the threshold gives roughly one alarm in five.
Every figure here is `ml/metrics.json`, which is committed — check it.

The baseline in that table is **engine temperature specifically**, because that is the
channel fleets alarm on today — not because it is the strongest threshold available. It
isn't, and we would rather say so than be caught: a rate-matched threshold on **vibration
slope**, which is one of the 26 features the model already receives, beats us badly at
long range — **53.7% at 72–96 h against our 7.3%**, with a median lead time of **108 h
against our 72 h**.

What that threshold buys in range it pays for in the window where dispatch decisions are
actually made. Across the held-out assets it catches **70–71%** of failures inside 72
hours where the model catches **93.8–100%**; it fires at least once on **18 of the 24
never-failing test machines** where the model fires on **0 of 24**; and only **89.8%** of
its alarms land inside a real degradation ramp against the model's **100%**. It is an
earlier, much noisier smoke detector. Neither is strictly better, and a fleet running this
for real should run both — the slope rule to populate a watch-list, the model to commit a
truck. (Reproduce both from `ml/train.py` and `ml/features.py`; the slope is feature 4 of
26, and the split is by asset with `numpy.random.default_rng(42)`.)

It answers *how soon* by asking the same question at 24 / 48 / 72 h and reporting the tightest horizon
it clears — the estimate comes from the models, never from the label.

### And *which part* — because "hardware fault" does not fill a van

Four components fail with different signatures across the same channels, which is what
makes them separable:

| Component | How it announces itself | Part |
|---|---|---|
| Hydraulic pump | vibration + metal in the oil, then pressure sags, heat only at the end | `HYD-PUMP-40L` |
| Cooling system | heat climbs early and keeps climbing; nothing else moves | `RADIATOR-CORE-XL` |
| Main bearing | vibration dominates from the start, some metal, little else | `BEARING-SET-90` |
| Alternator | purely electrical — charge voltage decays, mechanics stay normal | `ALTERNATOR-24V` |

Temperature is the *last* signal for the pump, the *only* signal for cooling, and never
moves for the alternator. A threshold returns a yes or a no, so no threshold on any
channel returns a *component* — this is the one step in the pipeline with no rule-shaped
alternative at all. A classifier over the
trailing window identifies the component at **88.3% accuracy (0.870 macro F1)**, and the
part on the work order follows from it — which is also why the nearest technician is
often not the right one. On synthetic data the AUC is
~1.0, which is why we don't quote it; the warning-time gap is the claim, and it follows from the
physics being modelled rather than the classifier being clever.

---

## Architecture

| Layer | What it does | Code |
|---|---|---|
| **Telemetry simulator** | Replays each asset's real dataset readings over WebSocket; injects fault/silence on cue | `backend/app/simulator/` |
| **Anomaly detector** | Flags a lost heartbeat, opens an incident, dispatches the agent | `backend/app/anomaly/` |
| **AI agent** | Autonomous closed-loop investigation; emits a step-by-step reasoning trace | `backend/app/agent/` |
| **Agent memory** | Records how each incident resolved per asset and per ~2 km map cell; promotes repeat offenders to known dead zones | `backend/app/agent/memory.py` |
| **Network as Code adapter** | Four CAMARA families — Device Status (reachability + roaming), Congestion Insights, Location Retrieval, Geofencing Subscriptions; live sandbox **or** dataset-backed mock, with mock-on-error fallback | `backend/app/nac/` |
| **Diagnosis** | 4-class "what broke?" — an auditable rule, with `ml/model.pkl` trained as a check on it (they agree on 100% of 15,000 rows) | `backend/app/ml/client.py` |
| **ML — prognosis** | Multi-horizon failure forecasting + component identification — the two questions no rule answers (`ml/forecast_model.pkl`, `ml/component_model.pkl`) | `backend/app/ml/forecast.py` |
| **Operator dashboard** | Fleet map, KPIs, incident feed, live agent trace, work orders, scenario control | `frontend/` |

### AI agent layer — Resource & Tooling Guide compliant

- **Framework:** Pydantic AI (Guide §2, code-first)
- **Model:** `openai/gpt-oss-120b` — open weights, served on Groq's free tier (Guide §3). Verified end
  to end; `groq:qwen/qwen3.8-27b` also works. Swappable via `LLM_MODEL`.
- CAMARA APIs and the ML models are registered as **tools the agent chooses to call** (Guide §11)
- **Failsafe, two layers** (Guide §11 graceful degradation): if the model stalls without a terminal
  decision the agent re-asks for it, and failing that the deterministic rule agent finishes the same
  incident. `AGENT_MODE=rule` skips the model entirely and looks identical on screen.

Every terminal action is a tool with fixed logic, so the model decides *whether* to dispatch, never
*what* a dispatch does — it cannot invent a technician, a part, or a location.

---

## Run it

Prereqs: Python 3.12+ (tested on 3.14), Node 20+.

```bash
# one-shot (Windows)
pwsh scripts/dev.ps1
```

or manually:

```bash
# backend  →  http://127.0.0.1:8000
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
cp ../.env.example ../.env
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# dashboard  →  http://127.0.0.1:5173
cd frontend
npm install
npm run dev
```

Then open the dashboard, pick an asset in **Scenario control**, and hit **Cellular blind spot** or
**Hardware fault**. Watch the agent trace and work orders update live. **Sensor fault** and
**Crossed the border (roaming)** exercise the other two silent-asset outcomes; **Leaving the site
(geofence)** walks a perfectly healthy machine west across the perimeter until the operator's
geofence catches it — no incident opened, one prevented.

### Configuration (`.env`)

| Var | Default | Meaning |
|---|---|---|
| `NAC_MODE` | `mock` | `mock` (dataset-backed) or `live` (Nokia sandbox, mock-on-error fallback) |
| `NAC_API_KEY`, `NAC_DEVICE_MAP` | — | Sandbox key + `EQ-0007:+3197...,` asset→MSISDN map for `live` |
| `AGENT_MODE` | `rule` | `rule` (deterministic) or `llm` (Pydantic AI + `LLM_MODEL`) |
| `LLM_MODEL` | `groq:openai/gpt-oss-120b` | Pydantic AI model string; must support tool calling |
| `GROQ_API_KEY` | — | Required for `AGENT_MODE=llm` with a Groq model |
| `SILENT_THRESHOLD_SECONDS` | `30` | Heartbeat age before an asset is flagged silent |

---

## Deploy it

The whole thing runs as **one container**: the image builds the dashboard and FastAPI
serves it, so there is a single URL and no separate frontend host.

```bash
docker build -t filo-sentinel .
docker run -p 8000:8000 filo-sentinel     # → http://localhost:8000
```

`render.yaml` is included for a one-click Render deploy (free tier — the service
sleeps after ~15 min idle and takes about a minute to wake, so open the link a few
minutes before anyone looks at it).

The public deployment defaults to `AGENT_MODE=rule` and `NAC_MODE=mock`: no API keys
sitting on a public URL, no free-tier quota to burn, and the flow is identical. Set
`GROQ_API_KEY` / `NAC_API_KEY` in the host's dashboard to switch the live LLM agent
and live CAMARA calls on.

To run single-service locally without Docker:

```bash
cd frontend && npm run build          # emits frontend/dist
cd ../backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000
```

---

## Verify

```bash
cd backend && .venv/Scripts/python -m pytest -q      # unit + closed-loop tests
python scripts/scenario_smoke.py                      # headless end-to-end, both scenarios
python ml/train.py                                    # both models + ml/metrics.json
curl -XPOST "http://127.0.0.1:8000/api/nac/live-check"   # a real call to the Nokia sandbox
curl "http://127.0.0.1:8000/api/fleet/health"            # predictive maintenance view
```

---

## Status

Prototype for the Phase 2 live demo. Working end to end: simulator → anomaly detection → agent →
CAMARA Device Reachability Status + Roaming + Congestion Insights → branch → ML → CAMARA Location
Retrieval (asset, then crew) → work order + technician routing → live dashboard, with a standing
CAMARA Geofencing subscription raising perimeter alerts alongside it and continuous failure
forecasting across the fleet.

Live CAMARA calls against the Nokia sandbox are verified and exposed in the dashboard — the
live-check panel shows all four families with their real endpoint paths and round-trip latency. The
fleet itself
is simulated and we say so: the sandbox issues a handful of test SIMs provisioned in Hungary, so they
cannot stand in for thirty machines on a NEOM site.

**Next:** exercise `AGENT_MODE=llm` (Pydantic AI + Groq — needs `GROQ_API_KEY`), rehearse against
[DEMO_SCRIPT.md](DEMO_SCRIPT.md), record the backup video.

## Team FILO

Faris Alshafie · Yazan Zarka · Yazan Abed · Omar Hawasheen
