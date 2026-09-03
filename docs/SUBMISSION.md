# HackerEarth submission — Prototype Phase

Copy-paste answers for each required field. Anything marked **YOU** needs a human.

---

## Title

```
FILO Asset Sentinel — Autonomous Fleet Diagnostics for Giga-Projects
```

## Theme

Smart Cities, Urban Safety & Mega-Project Infrastructure

## Parent Submission — **YOU**

Select your Phase 1 (Idea) submission.

---

## Description

```
When heavy equipment on a NEOM-scale site stops sending telemetry, nobody can tell
whether the machine broke down or simply drove into a cellular dead zone. The default
is to send a field engineer across the desert to find out — an expensive guess that
often ends with a mechanic standing next to a perfectly healthy excavator.

The reason this is hard is structural: you cannot diagnose a silent machine from the
machine, because it is silent. In our fleet data, 49% of silent-asset events are
network outages and 51% are genuine hardware failures — and no amount of on-board
sensing separates them. Only the operator's network knows whether it dropped the
device.

FILO Asset Sentinel is an autonomous diagnostic agent built on that insight.

The moment a heartbeat stops, the agent opens an incident and investigates on its own:

1. It calls CAMARA Device Reachability Status (Nokia Network as Code) to ask the
   network what it knows.
2. NOT_CONNECTED is ambiguous — a dead engine and a coverage hole look identical — so
   it weighs serving-cell signal strength and neighbour-cell failures to tell them
   apart. A device that is unreachable but had a strong radio link with no neighbour
   failures is a machine that died, not a network that dropped it.
3. It also calls CAMARA Device Roaming Status, because reachability alone cannot see
   the third case: a machine that is healthy and attached, but attached to somebody
   else. NEOM sits kilometres from Egyptian and Jordanian networks, so an asset
   working the site boundary can hand off to a foreign operator — at which point its
   telemetry APN stops routing to us while every on-board sensor reads normal. This
   is invisible to the device and invisible to reachability; only the operator's
   roaming view reveals it, and the correct response is a connectivity ticket.
4. Five outcomes follow, and only one sends a person: coverage gap, roamed out,
   transient dropout, sensor fault (a low-cost sensor kit), or a genuine hardware
   fault.
5. On a genuine fault: a diagnostic model classifies it and a component model names
   the failing part — hydraulic pump, cooling system, main bearing or alternator, at
   88.3% accuracy. CAMARA Location Retrieval then supplies network-verified
   coordinates for a device whose own GPS is dark.
6. Location Retrieval is called a second time, on the technicians' phones. Their
   handsets are devices on the same network, so the same API answers who is genuinely
   nearest right now rather than who the roster listed this morning. The work order
   routes to the nearest technician actually carrying that part — and records, in
   plain language, when a closer technician was passed over for not carrying it.

So the agent orchestrates two CAMARA API families across three distinct network
signals — Device Reachability Status, Device Roaming Status, Location Retrieval — and
makes four network calls per hardware incident, deciding for itself which to make and
in what order.

Alongside this, a forecasting model scores the whole fleet continuously for machines
heading toward failure. Bearing wear lifts vibration and oil-particle count days
before engine temperature moves, so at two to three days out the model flags 94% of
failures where a temperature threshold catches 2%.

The agent is built with Pydantic AI driving openai/gpt-oss-120b on Groq's free tier.
The CAMARA APIs and the ML models are registered as tools the agent decides when to
call — not buttons a user presses. Its reasoning is streamed to the operator dashboard
step by step, and every terminal action is a tool with fixed logic, so the model
chooses whether to dispatch but never what a dispatch does.

Live CAMARA calls against the Nokia sandbox are wired and demonstrable in the
dashboard. The fleet itself is simulated and we say so on screen: the sandbox issues a
handful of test SIMs provisioned in Hungary, which cannot stand in for thirty machines
across a desert site.
```

---

## Demo Link

Deployed single-service build. **YOU** — paste the URL after deploying (see
"Deploy it" in the README; `render.yaml` is ready for a one-click Render deploy).

If the deployment is not up in time, use a recorded walkthrough and say so plainly
rather than linking something broken.

## Repository URL

```
https://github.com/yazanz22/Nokia
```

Confirmed public.

## Video URL — **YOU**

Record one clean run of the demo script (`DEMO_SCRIPT.md`), upload unlisted to
YouTube, paste the link.

## Presentation — **YOU**

Update the Phase 1 deck to match what was built. The three claims worth leading with:
the network call is irreplaceable, the agent decides rather than executes, and
forecasting beats a threshold by days.

## Snapshots

`docs/screenshots/` — dashboard at rest, mid-investigation, and the closing frame
showing one false dispatch avoided alongside one dispatch issued.

## Source Code

```bash
git archive --format=zip -o filo-asset-sentinel-src.zip HEAD
```

About 7 MB, well inside the 50 MB cap. Excludes `node_modules`, `.venv` and `.env`.

---

## Instructions to Run

```
PREREQUISITES
  Docker, or Python 3.12+ and Node 20+.

OPTION 1 — Docker (single container, recommended)

  docker build -t filo-sentinel .
  docker run -p 8000:8000 filo-sentinel

  Open http://localhost:8000

OPTION 2 — from source

  cd backend
  python -m venv .venv
  .venv/Scripts/python -m pip install -r requirements.txt      # Windows
  # .venv/bin/pip install -r requirements.txt                  # macOS/Linux
  cd ../frontend && npm install && npm run build
  cd ../backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000

  Open http://localhost:8000

USING THE DEMO

  1. Pick an asset under "Simulate" and click "Cellular blind spot".
     The agent investigates on its own. Watch "Agent reasoning" on the right.
     Expected: incident closes as BLIND SPOT - NO DISPATCH, no work order raised.

  2. Pick a different asset and click "Hardware fault".
     Expected: the agent rules out the network, classifies the fault, retrieves
     network-verified coordinates, and raises a work order routed to the nearest
     technician carrying the right part.

  Do not reset between the two. The KPI bar then reads
  "1 false dispatch avoided" alongside "1 dispatch issued" — the same symptom
  producing two opposite correct decisions, which is the whole product.

  3. "Run live CAMARA check" makes a real call to the Nokia Network as Code sandbox
     and shows the response with round-trip latency.

  4. "Predictive maintenance" lists machines that have not failed yet, ranked by how
     soon the model expects them to, with the signals that moved.

DEFAULTS
  Runs with the deterministic agent and dataset-backed CAMARA, so it works with no
  API keys and no internet. To enable the live LLM agent and live CAMARA calls, set
  in .env (copy from .env.example):
      AGENT_MODE=llm     GROQ_API_KEY=<key>
      NAC_MODE=live      NAC_API_KEY=<key>

TESTS
  cd backend && .venv/Scripts/python -m pytest -q     # 13 tests
  python scripts/scenario_smoke.py                    # headless end-to-end
```
