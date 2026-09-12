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
often ends with a mechanic standing next to a perfectly healthy generator.

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
4. Five outcomes follow, and three of them send nobody: coverage gap, roamed out,
   transient dropout. The fourth, a sensor fault, is worth a technician carrying a
   low-cost telemetry sensor kit, which rides in the van and needs no depot stop; only
   the fifth, a genuine hardware fault, is worth a mechanic, a depot call and a spare
   part. The response is graded to what broke, not switched on and off.
5. On a genuine fault: a diagnostic model classifies it and a component model names
   the failing part — hydraulic pump, cooling system, main bearing or alternator, at
   88.6% accuracy. CAMARA Location Retrieval then supplies network-verified
   coordinates for a device whose own GPS is dark.
6. Location Retrieval is called a second time, on the technicians' phones. Their
   handsets are devices on the same network, so the same API answers who is genuinely
   nearest right now rather than who the roster listed this morning.
7. The named component is a pallet item, so it lives in one of two parts depots on the
   site rather than in a van. The journey is technician to depot to machine, and the
   work order goes to whoever arrives soonest across that whole run, which is regularly
   not the nearest person. It records who was closer and how many minutes later they
   would have got there, because on a map a dispatch that drives past somebody nearer
   looks like a bug. Stock is claimed at the moment of dispatch, so two faults needing
   the last alternator cannot both be promised it.

It also calls CAMARA Congestion Insights, which is what makes the coverage verdict
work against a real operator rather than only against our simulation. Device Status
reports attachment and nothing about radio conditions, so signal strength and
neighbour-cell counts arrive empty from a live network. Congestion Insights grades the
serving area instead of the device — so it still answers when the device is dark. A
machine that goes silent into a cell the operator already reports as congested is a
network failing; low congestion clears the network and sharpens the hardware verdict.
Where both sources exist the device-specific radio metrics win, because congestion only
ever describes the neighbourhood.

A fifth signal runs the other way. Everything above starts with a machine that has
already gone quiet; CAMARA Geofencing Subscriptions is how one stops going quiet in
the first place. The site perimeter is registered with the operator, and the network
pushes an event the moment an asset crosses it — no polling, and critically the
warning arrives while the machine is still healthy and still reporting. On a site
kilometres from Egyptian and Jordanian networks, that is the difference between
diagnosing a silence and preventing one. We count those separately as incidents
prevented, because nothing failed.

So the agent orchestrates four CAMARA API families across five distinct network
signals — Device Reachability Status, Device Roaming Status, Congestion Insights,
Location Retrieval and Geofencing Subscriptions. It makes five calls per hardware
incident, deciding for itself which to make and in what order, and holds one standing
subscription that calls us.

Alongside this, a forecasting model scores the whole fleet continuously for machines
heading toward failure. Bearing wear lifts vibration and oil-particle count days
before engine temperature moves, so at two to three days out the model flags 92.2% of
failures where a temperature threshold catches 19.6%. Past 72 hours neither works well
and the threshold is marginally better; ml/metrics.json reports all five horizons.

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

```
https://nokia-rhhp.onrender.com/
```

Live single-service deployment on Render — FastAPI serving the built dashboard, one
container behind one URL: trained ML models loaded, all
five scenario outcomes reproduce, and the "Run live CAMARA check" panel returns real
Nokia sandbox data from Device Status (both reachability and roaming), Congestion
Insights and Location Retrieval. The fourth family, Geofencing Subscriptions, registers a
real perimeter watch only when the service's `PUBLIC_BASE_URL` is set to its own public
address, because registering one hands the operator a callback URL. Without it the panel
registers nothing and says why, rather than guessing an address.

Verified 2026-09-13 00:55 Dubai on commit `ee240a1`: the live panel returned Device
Status (reachability and roaming), Congestion Insights and Location Retrieval from the
Nokia sandbox, and Geofencing Subscriptions listed one active perimeter watch on the
service's account.

Two things a reviewer should know, both deliberate:

- The **agent runs in deterministic mode** on the public URL. The LLM path is
  identical on screen and is exercised by `scripts/scenario_smoke.py`; running it on
  an open link would let one visitor drain a free-tier daily token budget and leave
  the demo answering nobody.
- The **fleet is simulated and the network layer is not.** The Nokia sandbox issues a
  handful of test SIMs provisioned in Hungary that always report reachable, so they
  cannot stand in for thirty machines across a NEOM-scale site. The fleet is replayed
  telemetry served through the identical CAMARA contract; the live panel is the same
  code path with one environment variable changed, and it is there so the integration
  can be checked rather than taken on trust.

The service sleeps after 15 minutes idle on Render's free plan and takes about a
minute to wake, so a scheduled health check keeps it warm through the review window
(`.github/workflows/keepalive.yml`).

`.github/workflows/tests.yml` runs the backend suite and the frontend build on every
push and pull request. It installs from `backend/requirements.lock.txt` rather than the
range file, and asserts before the suite that the committed models actually loaded as
trained — a scikit-learn mismatch makes an unpickle fail silently into a rule-based
fallback, which would otherwise make the suite *greener* rather than redder, because
the tests that need the forecast model skip themselves when it is unavailable.

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

About 3.7 MB zipped, well inside the 50 MB cap. Excludes `node_modules`, `.venv` and
`.env`.

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
     technician once the depot holding the part is factored into the journey. The
     card explains why a closer technician was passed over.

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
  cd backend && .venv/Scripts/python -m pytest -q     # 240 tests, no network needed
  cd .. && backend/.venv/Scripts/python scripts/scenario_smoke.py   # headless end-to-end

  The suite covers the closed loop end to end, the LLM agent path (driven by a
  scripted model, so it runs offline with no API key), work-order lifecycle,
  geofence perimeter events, congestion evidence, silence assessment, the ML
  client, fleet seeding, an investigation re-entry regression, and the guards on
  every terminal action.
```
