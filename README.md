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

---

## Architecture

| Layer | What it does | Code |
|---|---|---|
| **Telemetry simulator** | Replays each asset's real dataset readings over WebSocket; injects fault/silence on cue | `backend/app/simulator/` |
| **Anomaly detector** | Flags a lost heartbeat, opens an incident, dispatches the agent | `backend/app/anomaly/` |
| **AI agent** | Autonomous closed-loop investigation; emits a step-by-step reasoning trace | `backend/app/agent/` |
| **Network as Code adapter** | CAMARA Device Status + Location Retrieval; live sandbox **or** dataset-backed mock, with mock-on-error fallback | `backend/app/nac/` |
| **ML fault model** | 4-class classifier over telemetry features (`ml/train.py` → `ml/model.pkl`) | `backend/app/ml/`, `ml/` |
| **Operator dashboard** | Fleet map, KPIs, incident feed, live agent trace, work orders, scenario control | `frontend/` |

### AI agent layer — Resource & Tooling Guide compliant

- **Framework:** Pydantic AI (Guide §2, code-first)
- **Model:** Groq — Llama 3.3 70B (Guide §3, free tier), swappable to Gemini / Ollama via `LLM_MODEL`
- CAMARA APIs are registered as **tools the model chooses to call** (Guide §11), not buttons
- **Failsafe:** `AGENT_MODE=rule` runs the identical closed loop with no LLM call (Guide §11 graceful
  degradation). This is also the default while the Groq key is being provisioned.

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
cd backend && .venv/Scripts/python -m pytest -q          # unit + closed-loop tests
python scripts/scenario_smoke.py                          # headless end-to-end, both scenarios
curl "http://127.0.0.1:8000/api/debug/nac?asset_id=EQ-0005"   # prove a Network-as-Code call
```

---

## Status

Prototype for the Phase 2 live demo. Working end to end in `mock` mode: simulator → anomaly detection →
agent (rule mode) → CAMARA Device Status → branch → ML → CAMARA Location Retrieval → work order +
technician routing → live dashboard.

**Next:** train `ml/model.pkl` on `data/dataset1.csv`, wire `AGENT_MODE=llm` (Pydantic AI + Groq),
connect the live Nokia sandbox, demo-script rehearsal + backup recording.

## Team FILO

Faris Alshafie · Yazan Zarka · Yazan Abed · Omar Hawasheen
