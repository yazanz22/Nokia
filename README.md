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
   └─▶ CAMARA Device Status (Nokia Network as Code)   ── is the network up here?
         ├─ coverage gap ─▶ log blind spot, schedule re-check, notify operator   ✗ NO DISPATCH
         └─ network fine ─▶ ML fault model  ─▶  CAMARA Location Retrieval  ─▶  work order + nearest
                                                                                technician w/ the part
```

Every step of the agent's reasoning is streamed to a live operator dashboard.

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
| Unreachable · weak cell (≤ −105 dBm) · neighbour cells failing | coverage gap | re-check, **no dispatch** |
| Unreachable · **strong** cell · no neighbour failures | network is fine, so the machine died | classify fault → dispatch |
| Reachable · **roaming on a foreign operator** | crossed the border; telemetry can't reach us | connectivity ticket, **no dispatch** |
| Reachable · telemetry nominal | transient dropout | re-check, **no dispatch** |
| Reachable · telemetry age drifting | sensor fault | cheap sensor-kit dispatch |

The second row is the one a naive reachability check gets exactly backwards. The third
is invisible without the roaming API — the machine is healthy *and attached*, just not
to our network, so nothing on the device can tell you why its data stopped arriving.
NEOM sits within a few kilometres of Egyptian and Jordanian networks, so this is an
ordinary event on that site.

One dispatch among five outcomes. That ratio is the product.

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

Diagnosis is only half of it. `data/telemetry_history.csv` (from `data/history_builder.py`) is 30 days
of continuous per-machine telemetry with a physically ordered degradation ramp: bearing wear lifts
**vibration** and **oil-particle count** first, seals let **hydraulic pressure** sag next, and
**engine temperature** — the one signal a threshold alarm would watch — only spikes in the final hours.

So the forecasting model is scored on warning time, not accuracy:

| hours before failure | this model | engine-temp threshold |
|---|---|---|
| 48–72 h | **94%** | 2% |
| 24–48 h | **100%** | 1% |
| 0–24 h | 100% | 18% |

It answers *how soon* by asking the same question at 24 / 48 / 72 h and reporting the tightest horizon
it clears — the estimate comes from the models, never from the label. On synthetic data the AUC is
~1.0, which is why we don't quote it; the warning-time gap is the claim, and it follows from the
physics being modelled rather than the classifier being clever.

---

## Architecture

| Layer | What it does | Code |
|---|---|---|
| **Telemetry simulator** | Replays each asset's real dataset readings over WebSocket; injects fault/silence on cue | `backend/app/simulator/` |
| **Anomaly detector** | Flags a lost heartbeat, opens an incident, dispatches the agent | `backend/app/anomaly/` |
| **AI agent** | Autonomous closed-loop investigation; emits a step-by-step reasoning trace | `backend/app/agent/` |
| **Network as Code adapter** | CAMARA Device Status + Location Retrieval; live sandbox **or** dataset-backed mock, with mock-on-error fallback | `backend/app/nac/` |
| **ML — diagnosis** | 4-class classifier, "what broke?" (`ml/train.py` → `ml/model.pkl`) | `backend/app/ml/client.py` |
| **ML — prognosis** | Multi-horizon failure forecasting, "what is *about* to break?" (`ml/forecast_model.pkl`) | `backend/app/ml/forecast.py` |
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
**Hardware fault**. Watch the agent trace and work orders update live.

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
CAMARA Device Reachability Status → branch → ML → CAMARA Location Retrieval → work order + technician
routing → live dashboard, alongside continuous failure forecasting across the fleet.

Live CAMARA calls against the Nokia sandbox are verified and exposed in the dashboard. The fleet itself
is simulated and we say so: the sandbox issues a handful of test SIMs provisioned in Hungary, so they
cannot stand in for thirty machines on a NEOM site.

**Next:** exercise `AGENT_MODE=llm` (Pydantic AI + Groq — needs `GROQ_API_KEY`), rehearse against
[DEMO_SCRIPT.md](DEMO_SCRIPT.md), record the backup video.

## Team FILO

Faris Alshafie · Yazan Zarka · Yazan Abed · Omar Hawasheen
