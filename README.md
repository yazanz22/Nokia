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

## Why the network check matters

In the project dataset (`data/dataset1.csv`, 15k readings, 500 assets, NEOM / Gulf of Aqaba), **both**
a coverage outage and a dead engine present as `reachable = false`. Device Status alone is ambiguous.
The agent disambiguates with the extra signals CAMARA / connectivity-insights expose:

| Situation | reachable | serving-cell signal | neighbour-cell failures | engine temp | agent decision |
|---|---|---|---|---|---|
| `NETWORK_OUTAGE` | false | ≈ −120 dBm (weak) | 3–14 | normal | **coverage gap — no dispatch** |
| `DEVICE_FAILURE` | false | ≈ −50 dBm (strong) | 0 | 105–129 °C | **hardware fault — dispatch** |
| `SENSOR_FAILURE` | true | normal | 0 | normal | sensor kit — cheap dispatch |
| `NORMAL` | true | normal | 0 | normal | — |

The dataset is synthetic — `data/dataset_builder.py` generates it (500 assets, 4 labelled signal
signatures; `NORMAL` and `SENSOR_FAILURE` deliberately overlap so the ML task stays honest). The
committed `data/dataset1.csv` is the canonical copy everything is built and tested against.

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
| `LLM_MODEL` | `groq:llama-3.3-70b-versatile` | Pydantic AI model string |
| `GROQ_API_KEY` | — | Required for `AGENT_MODE=llm` with a Groq model |
| `SILENT_THRESHOLD_SECONDS` | `30` | Heartbeat age before an asset is flagged silent |

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
