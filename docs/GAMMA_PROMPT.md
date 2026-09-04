# Gamma AI prompts — FILO Asset Sentinel pitch deck

Gamma's free tier caps a generation at **10 cards**, so the deck is split into two
generations that get combined by hand: **Deck A (10 cards)** and **Deck B (6 cards)**.

## How to run this

1. In Gamma: **Create new → Paste in text**, paste **Prompt A**, set card count to **10**, generate.
2. **Note the theme Gamma applied** (the theme name is in the editor's side panel).
3. New generation: **Paste in text**, paste **Prompt B**, set card count to **6**, and — before
   generating — **pick the same theme by name**. Theme selection is a UI action; no prompt can do
   it for you, and it is the single thing most likely to make the seam visible.
4. Combine: in Deck A, use **Add card → Import / duplicate from another deck**, or export both to
   PowerPoint and paste Deck B's six slides after Deck A's ten.

The two style blocks below are **deliberately identical, word for word**. Don't edit one without
editing the other — that's what keeps the halves looking like one deck.

## Checks after generating

- Deck A must **not** end with a "thank you" or summary card — card 10 is the last one.
- Deck B must **not** start with a title or cover card — its card 1 is content.
- Gamma rounds numbers. Confirm **95.2%** and **88.3%** survived intact.
- Deck B card 3 must still read *targets*, not claims.
- Deck A cards 6, 7 and 9 must be a diagram, a table and a diagram — not three text blocks.
- Deck A card 8 must name **all three** signals. Gamma likes to compress it back to two
  (reachability + location) and drop roaming — which is the one signal nothing else can see, and
  the evidence card 7's roaming row depends on.
- **Theme match is not automatic — confirmed by an actual combine on 2026-09-03.** Two separate
  generations produced two visually unrelated decks (a light minimal sans-serif for A, a bold
  black condensed display face for B) even from the same style block. Picking the same theme by
  name in step 3 is not optional polish; skip it and the combined deck reads as two decks
  stapled together.
- **Gamma invents specific factual claims when a card has room, not just numbers — confirmed.**
  On the impact card it added "NEOM and Masdar City are required to report Scope 3 emissions on
  major projects" — a specific regulatory claim with no source anywhere in this prompt or in
  `docs/EVIDENCE.md`. It also turned "94% vs 2%" into a new headline stat, "47× more impending
  failures," by computing the ratio itself. Read every card's added sentences, not just its
  numbers, against the source content — a plausible-sounding claim that was never given is a
  fabrication regardless of whether a number changed.
- On a diagram slide, check reading order against the slide's own caption, not just left-to-right/
  top-to-bottom by default. A pyramid is conventionally read foundation-at-base — Layer 1 wide at
  the bottom, Layer 4 narrow at the top is *correct*, not backwards. A numbered step sequence is
  not: if the caption says "from X to Y," X must be first in reading order. Confirmed both patterns
  in the same deck — the architecture pyramid had the right layer order but mismatched badge
  numbers (badge "1" sitting on "Layer 4"); the decision-loop flow had correctly-numbered steps
  running in the wrong order for its own caption ("From heartbeat loss to verdict" reading
  Verdict-first).

Every figure below traces to `docs/EVIDENCE.md` or `ml/metrics.json`.

---

# PROMPT A — cards 1–10

```
You are helping build a pitch deck for a hackathon judging panel. Create a 10-card
presentation from the content below. This is the FIRST HALF of a longer deck; a second
set of cards will be appended afterwards.

STYLE
- Audience: telecom and enterprise judges at the GSMA MENA Ignite / MENA Open Gateway
  Hackathon. Technical, senior, sceptical of overclaiming.
- Tone: confident and concrete. Engineering credibility over marketing energy.
- Visual direction: dark industrial theme. Desert dusk palette — deep charcoal and
  slate backgrounds, high-visibility amber as the single accent colour, one cool teal
  for "healthy" states. Condensed sans-serif headings, monospace for any data,
  metrics or code. Think construction-site telemetry console, not SaaS landing page.
- Imagery: heavy construction equipment in desert terrain, cellular network coverage
  abstractions, telemetry dashboards. No stock photos of people in hard hats pointing
  at tablets. No generic "AI brain" or glowing-circuit imagery.
- Layout: prefer diagrams, decision tables and metric callouts over bullet lists.

RULES — IMPORTANT
- Use ONLY the facts and numbers given below. Do not invent, extrapolate or "round up"
  any statistic. If a card feels thin, make it more visual, not more speculative.
- Preserve the exact hedging language. Where the text says "target", "illustrative" or
  names a source, keep it. The honesty is deliberate and is part of what is being judged.
- Produce exactly 10 cards, one per CARD block below. Do not merge or split them.
- Do NOT add a closing, summary or thank-you card. The deck continues after card 10.
- Cards 6, 7 and 9 must be visual — a flow diagram, a table and a layered diagram
  respectively. Do not turn them into bullet lists.
- Add speaker notes to each card expanding on the argument for a live pitch.

---

CARD 1 — TITLE
FILO Asset Sentinel
Autonomous fleet diagnostics for giga-projects
Team FILO · Theme 2: Smart Cities, Urban Safety & Mega-Project Infrastructure
Powered by CAMARA Device Reachability Status, Device Roaming Status, Congestion Insights,
Location Retrieval and Geofencing Subscriptions, via Nokia Network as Code

CARD 2 — THE PROBLEM
A silent machine cannot tell you why it is silent.
When an excavator on a NEOM-scale site stops sending telemetry, the data that would
explain the silence is exactly the data that stopped arriving. Broken engine, failed
sensor, and cellular dead zone all look identical from the operations centre: nothing.
The default response is to send a technician to go and find out. That is a guess, and
it is wrong a large fraction of the time.

CARD 3 — WHAT THE GUESS COSTS
- A single truck roll costs $250–$1,000.
- Unplanned downtime on construction equipment runs $3,200–$8,700 per machine per day.
- In telecom field service, 17–20% of dispatches are "no fault found" — the technician
  arrives and there is nothing to fix. (Telecom consumer data, not construction; cited
  to show the problem class is real and budgeted, not to size our own impact.)
- 25% of service calls require a second visit because the first technician arrived
  without the right part. (Aberdeen Group)
- 73% of construction telematics runs over cellular — so coverage is a live variable,
  not an edge case.
At giga-project scale — hundreds of machines across thousands of square kilometres of
desert — that guesswork compounds into schedule, budget and crew-safety risk.

CARD 4 — THE INSIGHT
The network is the missing witness.
If the machine cannot tell you why it went quiet, ask the network that was carrying it.
The mobile operator knows whether that SIM is still attached, what its last serving-cell
signal was, whether neighbouring cells were failing, and whether it has roamed onto a
foreign network. None of that is visible to any on-board sensor, and no amount of better
telemetry hardware produces it — the device is dark.
This is why a standardised operator API is not a convenience here. It is the only source
of the deciding evidence.

CARD 5 — WHAT WE BUILT
An AI agent that investigates before anyone drives anywhere.
The moment a heartbeat stops, the agent opens an incident and runs its own investigation:
1. Query CAMARA Device Reachability Status — is the device still on the network?
2. "Not connected" is ambiguous: a dead engine and a coverage hole look the same. So it
   weighs serving-cell signal strength, neighbour-cell failures and roaming country to
   tell them apart.
3. Reach a verdict — only one of five outcomes sends a human.
4. If it is genuinely hardware, ML identifies the failing component, CAMARA Location
   Retrieval fixes the machine's true position, and the work order routes to the nearest
   technician actually carrying that part.
No human triage at any stage.

CARD 6 — THE DECISION LOOP (make this a horizontal flow diagram)
Heartbeat lost → CAMARA Device Reachability → Disambiguate signal / neighbour cells /
roaming → Verdict → [4 of 5 paths: no dispatch] or [1 path: ML component diagnosis →
CAMARA Location Retrieval → work order to nearest technician carrying the part]
Caption: Four of the five outcomes end without sending anyone. That is the product.

CARD 7 — FIVE OUTCOMES, ONE DISPATCH (make this a table)
Columns: Situation | Network evidence | Action
- Coverage gap | Unreachable, weak last signal, neighbour-cell failures | Log blind spot,
  schedule re-check, notify operator — NO DISPATCH
- Roamed across the border | Reachable, but Device Roaming Status reports an EG/JO
  network | Connectivity ticket — NO DISPATCH
- Transient dropout | Reachable, telemetry nominal | Re-check — NO DISPATCH
- Sensor fault | Reachable, machine healthy, telemetry channel dead | Low-cost sensor
  kit dispatch
- Hardware fault | Reachable or strong last signal, no network cause | ML names the
  component → dispatch with the right part
Caption: NEOM sits at the head of the Gulf of Aqaba, kilometres from Egyptian and
Jordanian networks. Border roaming is a real event on this site, not a hypothetical —
and it is invisible to every on-board sensor.

CARD 8 — THE CAMARA APIS
Four API families. Five network signals. Four we ask, one asks us.
1. Device Reachability Status — the truth layer. The authoritative answer to "is this
   device still on the network?" the moment telemetry stops. It converts an ambiguous
   silence into a decision.
2. Device Roaming Status — the signal nothing else can see. A machine can be healthy,
   attached and still silent, because it attached to somebody else's network. Working
   the site boundary at NEOM, an asset can hand off to an Egyptian or Jordanian
   operator; its telemetry APN then stops routing to us while every on-board sensor
   reads perfectly normal. Invisible to the device. Invisible to reachability. Only the
   operator's roaming view reveals it.
3. Congestion Insights — the evidence that survives a dark device. Device Status
   reports attachment and nothing about radio conditions, so against a real operator
   signal strength and neighbour-cell counts arrive empty. This grades the serving
   area instead of the device, which is why it still answers when the device has gone
   silent: a machine that goes quiet into a cell the operator already reports as
   congested is a network failing, not a machine failing.
4. Geofencing Subscriptions — the only one that runs the other way. Everything else
   here starts with a machine that has already gone quiet. This registers the site
   perimeter with the operator, and the network pushes an event the moment an asset
   crosses it — so the warning arrives while the machine is still healthy and still
   reporting, before it drives into foreign coverage and goes dark. Diagnosing a
   silence versus preventing one.
5. Location Retrieval — used twice, for two different questions. Once for the silent
   machine, whose own GPS is dark or untrustworthy. Once for the crew: a technician's
   phone is a device on the same network, so the same call answers who is genuinely
   nearest right now, not who the roster listed this morning.
The agent decides which of these to call and in what order — they are tools, not steps
in a script. All delivered through Nokia Network as Code, GSMA Open Gateway compliant,
and therefore carrier-portable rather than locked to one telematics vendor.

CARD 9 — ARCHITECTURE (make this a layered diagram, top to bottom)
1. Data ingestion & telemetry — CAN-bus, engine temperature, vibration, battery voltage,
   GPS streamed from every connected asset
2. AI agent & orchestration — autonomous triage; the agent chooses which tools to call
   and in what order
3. Network as Code integration — CAMARA Device Reachability Status and Location Retrieval
4. Action & dashboard — work-order generation, technician routing, live operations view

CARD 10 — THE AGENT DECIDES, IT DOES NOT EXECUTE
A design decision worth stating plainly.
The language model chooses which evidence to gather and in what order. It does not get to
invent the conclusion. Every terminal action — dispatch, blind-spot resolution, roaming
ticket — is a tool with fixed logic that independently re-derives the verdict from the
network evidence before it will act.
So the model can reason freely, and still cannot dispatch a technician to a machine that
the network says is simply out of coverage. Autonomy where it adds judgement; determinism
where it would add risk.
```

---

# PROMPT B — cards 11–16

```
You are helping build a pitch deck for a hackathon judging panel. Create a 6-card
presentation from the content below.

CRITICAL: these cards are the SECOND HALF of an existing deck and will be appended
directly after it. Do NOT create a title card, cover card, agenda card or introduction.
Card 1 below is a content card and must be the first card you produce. The audience has
already seen the problem statement, the architecture and the API design — do not
re-introduce the product or re-explain what it does.

STYLE
- Audience: telecom and enterprise judges at the GSMA MENA Ignite / MENA Open Gateway
  Hackathon. Technical, senior, sceptical of overclaiming.
- Tone: confident and concrete. Engineering credibility over marketing energy.
- Visual direction: dark industrial theme. Desert dusk palette — deep charcoal and
  slate backgrounds, high-visibility amber as the single accent colour, one cool teal
  for "healthy" states. Condensed sans-serif headings, monospace for any data,
  metrics or code. Think construction-site telemetry console, not SaaS landing page.
- Imagery: heavy construction equipment in desert terrain, cellular network coverage
  abstractions, telemetry dashboards. No stock photos of people in hard hats pointing
  at tablets. No generic "AI brain" or glowing-circuit imagery.
- Layout: prefer diagrams, decision tables and metric callouts over bullet lists.

RULES — IMPORTANT
- Use ONLY the facts and numbers given below. Do not invent, extrapolate or "round up"
  any statistic. If a card feels thin, make it more visual, not more speculative.
- Preserve the exact hedging language. The impact card states targets, not results, and
  must keep saying so. The honesty is deliberate and is part of what is being judged.
- Produce exactly 6 cards, one per CARD block below. Do not merge or split them.
- Card 1 must be a metrics card — three model results as prominent stat callouts.
- Add speaker notes to each card expanding on the argument for a live pitch.

---

CARD 1 — THE MACHINE LEARNING (three prominent stat callouts)
Three models, each answering a different question.
- What broke? Diagnostic classifier — 95.2% accuracy, 0.907 macro F1. Ceiling is
  deliberate: two classes overlap by design in our data, so the model cannot be a
  suspiciously perfect 100%.
- Which part? Component classifier — 88.3% accuracy, 0.870 macro F1, across four
  components with distinct degradation signatures. This is what turns a work order from
  "go look at it" into "bring this part".
- When will it break? Prognostic model — catches 94% of failures 48–72 hours ahead,
  against 2% for a conventional engine-temperature threshold on the same data.
Note on the last figure: that is our model on our dataset. The generators are in the repo.

CARD 2 — THE AGENT LEARNS THE SITE
Every resolution is recorded against the asset and a ~2 km map cell.
When a second and third incident resolve as coverage failures in the same cell, the agent
stops treating it as news: that area is a known dead zone, it is drawn on the operations
map, and future silences there are triaged against what the site has already taught it.
A construction site's coverage map changes as the site is built. The system learns the
terrain instead of re-deriving it every time.

CARD 3 — IMPACT
Targets, stated as targets.
- 40% reduction in false dispatches
- 25% reduction in downtime
- 15% OpEx reduction across fuel, labour hours and premature part replacement
These are design targets, not measurements — we have not yet run on a real fleet. What
supports them: predictive maintenance programmes are independently reported to cut
maintenance costs 18–25% and downtime by up to 50% (McKinsey, Deloitte).
Beyond cost: fewer needless journeys means fewer crew-hours in extreme-heat remote
terrain, and a measurably lower project carbon footprint — which matters to ESG-committed
developers like NEOM and Masdar City.

CARD 4 — BUSINESS MODEL
Target customers: main contractors, master developers and heavy-equipment rental fleets
across the MENA giga-project corridor — NEOM and Red Sea Global, Qiddiya, Masdar City,
Msheireb Doha.
Two revenue streams:
- Tiered SaaS subscription, priced per connected asset per month — scales with fleet size
  and site expansion.
- Value-based API premium, priced on automated decision volume — customers pay in
  proportion to the dispatches avoided.
Cost structure: cloud-native and serverless, on pay-per-use telecom APIs. Infrastructure
scales with demand rather than ahead of it.
Why it travels: because it is built on GSMA Open Gateway rather than one vendor's
telematics stack, the same integration works across operators and across markets.

CARD 5 — STATUS & ROADMAP
Working today: the full closed loop runs end to end — live telemetry simulation over a
real equipment dataset, autonomous agent investigation, verified live calls against the
Nokia Network as Code sandbox, ML diagnosis and prognosis, automated work-order routing,
and a live operations dashboard.
Next: pilot deployment with regional operator partners on active giga-project sites —
real fleet data, real network conditions, real coverage holes.

CARD 6 — TEAM FILO
Yazan Zarka — Software Engineer. Backend systems and CAMARA API integration.
Faris Alshafie — Software Engineer. Cloud architecture and the operations dashboard.
Yazan Abed — Data Scientist. Predictive maintenance modelling and anomaly detection.
Omar Hawasheen — Data Scientist. AI agent orchestration and decision logic.
Closing line, displayed prominently: You cannot diagnose a silent machine from the
machine. So we asked the network.
```
