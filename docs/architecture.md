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
tell you.

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
│     agent decides when to call. Emits a reasoning trace per step.    │
│     backend/app/agent/                                               │
└───┬───────────────────┬───────────────────┬──────────────────────────┘
    │                   │                   │
┌───▼──────────┐  ┌─────▼────────┐  ┌───────▼────────────┐
│ 4. NETWORK   │  │ 5. ML        │  │ 6. OPERATIONS      │
│ AS CODE      │  │              │  │                    │
│ Reachability │  │ diagnose:    │  │ work order,        │
│ Status v1    │  │  what broke  │  │ nearest technician │
│ Location     │  │ forecast:    │  │ carrying the part, │
│ Retrieval v0 │  │  what will   │  │ ETA, routing       │
│ Roaming      │  │              │  │                    │
│ app/nac/     │  │ app/ml/      │  │ app/agent/tools.py │
└──────────────┘  └──────────────┘  └────────────────────┘
```

## The decision the agent actually makes

`NOT_CONNECTED` is ambiguous on its own — it is what a dead engine and a coverage
hole both look like. The agent resolves it from signals the device cannot provide:

| Observation | Reading | Action |
|---|---|---|
| Unreachable, weak serving cell (≤ −105 dBm), neighbour cells also failing | coverage gap | re-check scheduled, operator notified, **no dispatch** |
| Unreachable, **strong** serving cell, no neighbour failures | the network is fine here, so the machine died | ML classifies the fault → dispatch |
| Reachable, telemetry nominal | transient dropout | re-check, **no dispatch** |
| Reachable, telemetry age drifting | sensor fault | cheap sensor-kit dispatch |

The middle row is the interesting one: *unreachable but with a healthy radio link* is
the case a naive "is it reachable?" check gets exactly backwards.

## Where ML earns its place

Not in diagnosis. On this data a single engine-temperature threshold separates
hardware failure from network outage cleanly, and we say so rather than overclaiming.

It earns its place in **forecasting**, because the signals that matter arrive in
physical order. Bearing wear lifts vibration and oil-particle count days out; seals
let hydraulic pressure sag next; engine temperature — the only channel a threshold
alarm watches — moves in the final hours.

| Hours before failure | This model | Engine-temp threshold |
|---|---|---|
| 48–72 h | **94%** | 2% |
| 24–48 h | **100%** | 1% |
| 0–24 h | 100% | 18% |

Horizon comes from asking the same question at 24 / 48 / 72 h and reporting the
tightest one the model clears — never from the label.

## Failure behaviour

Every layer degrades rather than breaks, because a demo and a construction site have
that requirement in common.

| If this fails | What happens |
|---|---|
| Nokia sandbox unreachable | per-call fallback to dataset-backed CAMARA, identical contract |
| LLM stalls without deciding | agent re-asks for the terminal call, then the deterministic agent finishes the incident |
| No model files present | transparent rule-based classifier with the same interface |
| Model returns `NORMAL` | dispatch is refused inside the tool — a healthy reading can never become a work order |
| Fleet reset mid-investigation | in-flight work is cancelled and abandoned, never written to the fresh state |

## Honest boundaries

- The **fleet is simulated.** The Nokia sandbox issues a handful of test SIMs
  provisioned in Hungary; they cannot stand in for thirty machines across a NEOM
  site, and a live location lookup would route every dispatch to Budapest. The
  dashboard's live-CAMARA panel makes real calls and says exactly this on screen.
- The **datasets are synthetic**, generated by `data/dataset_builder.py` and
  `data/history_builder.py`, both in the repo. Figures computed from them describe
  the model's behaviour, not evidence about the world.
- State is **in-memory**: a restart resets the fleet. Deliberate for a demo, and the
  first thing a pilot would replace.
