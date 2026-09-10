# Gamma AI prompts — FILO Asset Sentinel pitch deck

Gamma's free tier caps a generation at **10 cards**, so the deck is split into two
generations that get combined by hand: **Deck A (10 cards)** and **Deck B (7 cards)**.

Rewritten for **Phase 2 judging**. The previous version was a technical deck with no market
case at all; this one carries the commercial argument the supervisor review asked for
(market sizing, who pays, validated assumptions) without dropping the engineering spine the
"Technical Feasibility" and "Agentic AI & Multi-API Orchestration" criteria are scored on.
The previous version is in git history if a card needs to be pulled back.

## How to run this

1. In Gamma: **Create new → Paste in text**, paste **Prompt A**, set card count to **10**, generate.
2. **Note the theme Gamma applied** (the theme name is in the editor's side panel).
3. New generation: **Paste in text**, paste **Prompt B**, set card count to **7**, and — before
   generating — **pick the same theme by name**. Theme selection is a UI action; no prompt can do
   it for you, and it is the single thing most likely to make the seam visible.
4. Combine: in Deck A, use **Add card → Import / duplicate from another deck**, or export both to
   PowerPoint and paste Deck B's seven slides after Deck A's ten.

The two style blocks below are **deliberately identical, word for word**. Don't edit one without
editing the other — that's what keeps the halves looking like one deck.

## Checks after generating

- Deck A must **not** end with a "thank you" or summary card — card 10 is the last one.
- Deck B must **not** start with a title or cover card — its card 1 is content.
- Gamma rounds numbers. Confirm **92.2%**, **88.6%**, **95.2%** and **$1.66M** survived intact.
- Deck B card 1 must keep the diagnostic step framed as a *rule* that a model reproduces
  exactly, not as an ML result. Gamma likes to promote 95.2% to the headline stat because
  it is the biggest number on the card — if it does, that is precisely the claim a judge
  can refute from our own repo. Demote it back to third.
- **Deck B card 2 is the card most likely to be sanded down, and it is the one that must
  survive intact.** It says our own numbers are unvalidated. Gamma treats that as a
  weakness to soften and will quietly turn "we have not run a field trial" into "early
  results are promising". If any hedge has gone, put it back — that card is the direct
  answer to the supervisor's sharpest note and it is worth more than any claim on it.
- Deck B card 3 must keep TAM/SAM/SOM labelled with their sources and must **not** gain a
  revenue projection. Gamma likes to add a hockey-stick "Year 1 / Year 3 / Year 5" row. We
  have no such forecast; anything it adds there is fabricated.
- **Deck B card 7 is the sources card, and its whole value is that every entry is real.**
  Check each link against the list in the prompt rather than skimming: a generator that
  shortens a URL, "tidies" a domain or invents a plausible-looking one has produced a
  citation to nothing, on the card whose entire purpose is being checkable. Confirm the
  count too — if fewer entries came out than went in, it has merged some.
- Deck A cards 6, 7 and 9 must be a diagram, a table and a layered diagram — not three text blocks.
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
  `docs/EVIDENCE.md`. It also computed a ratio of its own from the warning-time figures and
  put it on a card as "47× more impending failures". That ratio was never given to it, and
  against the current numbers it would be ~4.8× — so a deck still carrying "47×" is quoting
  a figure that was both invented and is now wrong. Read every card's added sentences, not just its
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

## Where each figure comes from

Two different standards of evidence are in this deck, and they are not interchangeable.

**Repo-traceable — verified against the source of truth in this repository:**
`ml/metrics.json` (92.2%, 88.6%, 95.2%, F1 1.00), `ml/baselines.json` (the 72 h bound and the
vibration-slope counter-argument), `docs/EVIDENCE.md` (every sourced cost figure and the
savings model's inputs), `data/dataset1.csv` (the 51/49 split — 2,309 `DEVICE_FAILURE` rows against 2,203
`NETWORK_OUTAGE` rows out of 15,000).

**Third-party market sizing — taken from `source_docs/FILO_Asset_Sentinel_Slides.md` and its
reference list.** The TAM/SAM/SOM figures on Deck B card 3 come with source URLs but have **not**
been independently re-checked against those pages. Before this deck is submitted, open the four
links behind the market numbers and confirm the figures and their years still read as stated.
Every other number in the deck traces to a file in this repo.

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
- Imagery: unattended industrial plant in desert and port terrain — generators, pump
  sets, compressors, light towers standing alone; cellular network coverage
  abstractions; telemetry dashboards. No stock photos of people in hard hats pointing
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
Autonomous diagnostics for unattended industrial assets
Team FILO · Theme 2: Smart Cities, Urban Safety & Mega-Project Infrastructure
Powered by CAMARA Device Reachability Status, Device Roaming Status, Congestion Insights,
Location Retrieval and Geofencing Subscriptions, via Nokia Network as Code

CARD 2 — ONE PROBLEM
A silent asset cannot tell you why it is silent.
Every machine in this fleet runs unattended — generators, pump sets, air compressors,
light towers, hydraulic power packs, welder sets. Nobody sits in them. They run overnight
and between shifts, and when one stops reporting there is no operator to radio in.
The data that would explain the silence is exactly the data that stopped arriving. A
seized engine, a failed sensor and a cellular dead zone are the same event from the
operations centre: nothing.
The default response is to send a technician to go and find out. That is a guess.
This deck is about that one guess. Everything else we built exists to remove it.

CARD 3 — WHAT THE GUESS COSTS
- A single truck roll costs $250–$600, and in some cases as high as $1,000.
  (Automation Anywhere)
- In telecom field service, 17–20% of dispatches are "no fault found" — the technician
  arrives and there is nothing to fix. (TechSee, the vendor's own experience rather than
  a third-party study.) This is telecom consumer data, not construction. We cite it to
  show the problem class is real, measured and already carries a budget line. We do NOT
  claim this rate for industrial fleets.
- Unplanned downtime runs $3,200–$8,700 per machine per day. (FleetRabbit, vendor)
- 25% of service calls need a second visit because the first technician arrived without
  the right part. (Aberdeen Group, 2013)
- 73% of construction and heavy-equipment telematics runs over cellular — so coverage is
  a live variable, not an edge case. (Market.us)
At giga-project scale — hundreds of assets across thousands of square kilometres — that
guesswork compounds into schedule, budget and crew-safety risk.

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
3. Reach a verdict — three of five outcomes send nobody, and the two that do are graded
   to what broke: a cheap sensor kit, or a mechanic with the right part.
4. If it is genuinely hardware, ML identifies the failing component, CAMARA Location
   Retrieval fixes the machine's true position, and the work order routes to the nearest
   technician once the depot holding that part is part of the journey.
No human triage at any stage.

CARD 6 — THE DECISION LOOP (make this a horizontal flow diagram)
Heartbeat lost → CAMARA Device Reachability → Disambiguate signal / neighbour cells /
roaming → Verdict → [3 of 5 paths: no dispatch] or [1 path: low-cost sensor kit] or
[1 path: ML component diagnosis → CAMARA Location Retrieval → work order to nearest
technician once the depot stop is counted]
Caption: Three of the five outcomes end without sending anyone, and the fourth sends a
sensor kit rather than a mechanic. Grading the response, not just gating it, is the product.

CARD 7 — FIVE OUTCOMES, TWO GRADED DISPATCHES (make this a table)
Columns: Situation | Network evidence | Action
- Coverage gap | Unreachable, weak last signal, neighbour-cell failures | Log blind spot,
  schedule re-check, notify operator — NO DISPATCH
- Roamed across the border | Reachable, but Device Roaming Status reports a Jordanian
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
   the site boundary at NEOM, an asset can hand off to a Jordanian operator; its
   telemetry APN then stops routing to us while every on-board sensor reads perfectly
   normal. Invisible to the device. Invisible to reachability. Only the operator's
   roaming view reveals it.
3. Congestion Insights — the evidence that survives a dark device. Device Status
   reports attachment and nothing about radio conditions, so against a real operator
   signal strength and neighbour-cell counts arrive empty. This grades the serving
   area instead of the device, which is why it still answers when the device has gone
   silent.
4. Geofencing Subscriptions — the only one that runs the other way. Everything else
   here starts with a machine that has already gone quiet. This registers the site
   perimeter with the operator, and the network pushes an event the moment an asset
   crosses it — so the warning arrives while the machine is still healthy and still
   reporting. Diagnosing a silence versus preventing one.
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
   and in what order, and records every resolution against the asset and a ~2 km map
   cell, so a cell that has resolved as a coverage failure three times becomes a known
   dead zone the site has taught it
3. Network as Code integration — four CAMARA families, five signals: Device Reachability
   Status, Device Roaming Status, Congestion Insights, Location Retrieval (asset and crew),
   and Geofencing Subscriptions, which pushes to us
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

# PROMPT B — cards 11–17

```
You are helping build a pitch deck for a hackathon judging panel. Create a 7-card
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
- Imagery: unattended industrial plant in desert and port terrain — generators, pump
  sets, compressors, light towers standing alone; cellular network coverage
  abstractions; telemetry dashboards. No stock photos of people in hard hats pointing
  at tablets. No generic "AI brain" or glowing-circuit imagery.
- Layout: prefer diagrams, decision tables and metric callouts over bullet lists.

RULES — IMPORTANT
- Use ONLY the facts and numbers given below. Do not invent, extrapolate or "round up"
  any statistic. If a card feels thin, make it more visual, not more speculative.
- Preserve the exact hedging language. Cards 2 and 5 state what we have NOT proved and
  must keep saying so, in those words. Do not soften "we have not run a field trial",
  "target", "illustrative" or "unvalidated" into anything warmer. The honesty is
  deliberate and is part of what is being judged.
- Do not add any revenue forecast, growth projection or year-by-year table. None exists.
- Produce exactly 7 cards, one per CARD block below. Do not merge or split them.
- Card 1 must be a metrics card — three model results as prominent stat callouts.
- Card 3 must be a funnel or tiered diagram (TAM → SAM → SOM).
- Add speaker notes to each card expanding on the argument for a live pitch.

---

CARD 1 — THE MACHINE LEARNING (three prominent stat callouts)
Three questions, and we are precise about which two need a model.
- When will it break? Prognostic model — catches 92.2% of failures 48–72 hours ahead,
  against 19.6% for the engine-temperature threshold fleets alarm on today.
  (~4.8x, not 47x. Say the horizon out loud: the advantage is inside 72 hours, which is
  what the models were trained for, and past that the threshold is better. A
  rate-matched vibration-slope threshold beats us past 72 hours — it is in our repo, in
  ml/baselines.json, and we volunteer it.)
- Which part? Component classifier — 88.6% accuracy, 0.872 macro F1, across four
  components with distinct degradation signatures. This is what turns a work order from
  "go look at it" into "bring this part". A threshold returns a yes or a no, never a part
  number — this step has no rule-shaped alternative at all.
- What broke? Not machine learning, and we say so. Diagnosis is a transparent rule of a
  couple of dozen lines. A classifier trained on the same 15,000 rows agrees with that
  rule on 100% of them, both scoring 95.2% on held-out assets — so 95.2% is the rule's
  number, not a model's. We keep the model as a check on the rule and run the rule,
  because a decision that sends a crew into the desert should be one a site manager can
  read and argue with.
Note on the first figure: that is our model on our dataset. The generators are in the repo.

CARD 2 — THE NUMBER WE ARE MOST OFTEN ASKED, AND WHAT IT IS REALLY WORTH
On our test data the agent identifies network-caused silence with an F1 of 1.00 across
3,791 held-out rows. It never sends anyone for a coverage gap.
We do not price at 1.00, and here is why. The dataset is ours, and it is separable
enough that a hand-written rule reproduces the model's answer on all 15,000 rows. An F1
of 1.00 measures our generator, not a desert. So we plan against an 80% capture rate — a
fifth of our own best result discounted away for a field that is messier than any
dataset — and we label it a target, not a finding.
Two more assumptions we are not pretending are findings:
- Our simulator assumes a near-even split between hardware faults and network causes
  (2,309 against 2,203 rows). That is a modelling choice, not a measurement of any real
  fleet. Validating it is the first question in our customer interviews.
- The 17–20% no-fault-found rate is telecom, not industrial. We use it to show the
  problem class is budgeted, never to size our own impact.
The gap between 1.00 on our bench and 40% in our pricing is exactly what a pilot buys.
That is the ask.

CARD 3 — THE MARKET (make this a TAM → SAM → SOM funnel diagram)
Bottom-up, and sourced.
- TAM — global predictive maintenance: $14.6–15.1B (2025).
  (Market Research Future / Straits Research / Precedence Research)
- SAM — where unattended assets sit on operator networks in our region: smart ports
  ($4.0B in 2024, forecast $39.1B by 2033, Grand View Research) + Saudi smart cities
  ($5.1B, forecast $10.9B by 2030, MarketsandMarkets) + maritime and port-equipment
  predictive maintenance ($1.22B, forecast $2.87B by 2030).
- SOM — one division or one terminal. Pilot-sized, low single-digit millions in year one.
Why ports belong in the same product and not a different one: a container terminal runs
the same unattended plant as a construction site — gensets, pump sets, compressors,
reefer power — on the same operator networks, with the same ambiguity when one goes
quiet. Port of NEOM Terminal 1 opens in 2026 with automated cranes.
The same argument extends to oil and gas, mining, utilities and logistics: remote assets,
coverage gaps, expensive dispatches.

CARD 4 — WHO PAYS, AND WHY NOT THE INCUMBENT
Primary customer: giga-project operators and terminal operators — NEOM, Port of NEOM,
Red Sea Global, Qiddiya, Masdar City, Msheireb Doha. Also main contractors and
heavy-equipment rental fleets across the same corridor.
The buyer is a person, not an organisation: the field operations manager or maintenance
supervisor who owns the dispatch budget and gets called when a crew comes back having
found nothing.
Where we sit against what already exists — this space is not empty and we do not pretend
it is:
- C3 AI, Siemens, traditional SCADA: predictive maintenance from on-board sensors. They
  are strong at "this asset is degrading". They cannot tell you why an asset went silent,
  because a silent asset has stopped feeding them.
- Onomondo: genuine network-level device diagnostics — through one vendor's SIMs and
  network. A giga-project runs subcontractor fleets on stc, Mobily and e&.
- Ookla: coverage measurement and analytics, not a per-device verdict something acts on.
- Esri / ArcGIS: renders the site and the fleet superbly. A human still decides whether
  to roll the truck.
Our angle is the combination, not any one part: carrier-agnostic standard APIs, an agent
that decides rather than a dashboard that displays, and a loop that closes on a named
part rather than an alert. These are characterisations of product category from public
materials — not benchmarks. We have run no comparison and quote no performance figures
for any of them.

CARD 5 — THE ECONOMICS
Illustrative arithmetic, not a measurement. Written out so the assumptions are arguable
rather than hidden inside a headline.
Mid-sized fleet, 30 technicians, midpoint assumptions (3.5 truck rolls per technician per
day, 252 working days, 18.5% no-fault-found, $425 per roll):
- 26,460 dispatches a year, of which about 4,895 find nothing wrong
- That is $2.08M a year spent arriving at machines that did not need anyone
- At our 80% target capture rate: $1.66M a year avoided
Priced at $30 per asset per month, a 500-asset fleet pays $180k a year — about 9.2x
covered by avoided dispatches alone, before any downtime saving is counted.
Second stream, stated per event rather than multiplied out: catching a failure early
converts an emergency repair into a planned one, and unplanned work costs 3-5x planned.
One avoided downtime day is worth $3,200-$8,700. We deliberately do not multiply that by
a fleet-wide failure rate — we could not source one, and inventing it would make the
total soft in a way you could not see.
Every input here is someone else's published figure except the capture rate, the fleet
headcount and the price point, which are ours and are labelled rather than buried.

CARD 6 — TEAM FILO AND THE ASK
Yazan Zarka — Software Engineer. Backend systems and CAMARA API integration.
Faris Alshafie — Software Engineer. Cloud architecture and the operations dashboard.
Yazan Abed — Data Scientist. Predictive maintenance modelling and anomaly detection.
Omar Hawasheen — Data Scientist. AI agent orchestration and decision logic.
Working today, end to end: live telemetry simulation over a real equipment dataset,
autonomous agent investigation, verified live calls against the Nokia Network as Code
sandbox, ML diagnosis and prognosis, automated work-order routing, live dashboard.
The ask: one pilot, at one NEOM division or one Port of NEOM terminal, to replace our
assumptions with their numbers.
Closing line, displayed prominently: You cannot diagnose a silent machine from the
machine. So we asked the network.

CARD 7 — SOURCES
Reference card. Dense, small type, multi-column, no imagery — this one is for reading,
not for presenting. Group under the headings given and keep every URL exactly as written.
Title it "Sources" and add a one-line standfirst: "Every figure in this deck, and where
it came from."

OUR OWN MEASUREMENTS — reproducible from the repository at github.com/yazanz22/Nokia
- Model results, all horizons, and the diagnostic F1 of 1.00 — ml/metrics.json
- The vibration-slope counter-argument we volunteer against ourselves — ml/baselines.json
- The 51/49 hardware/network split in our simulator — data/dataset1.csv
- Every sourced figure below, with its caveats — docs/EVIDENCE.md

COST OF A WASTED DISPATCH
- Truck roll $250-$600, up to $1,000; and the 25% second-visit figure, which is Aberdeen
  Group (2013) quoted there — automationanywhere.com/company/blog/rpa-thought-leadership/fixing-telecommunications-field-service
- No-fault-found 17-20% of dispatches — techsee.com/blog/save-millions-lowering-no-fault-found-nff-dispatch-rate/
  (the vendor's own experience, not a third-party study)
- Truck rolls per technician per day, 2-5 — smarty.com/articles/truck-roll-costs
  (worded by its source as an assumption, and describing telecom)

COST OF DOWNTIME
- $3,200-$8,700 per machine per day — fleetrabbit.com/industry/construction-management-system/real-cost-construction-equipment-downtime
- Unplanned downtime costs 3-5x planned — forconstructionpros.com/equipment-management/article/21104195/the-true-cost-of-unplanned-equipment-downtime
- Predictive maintenance cuts costs 18-25% and downtime up to 50% (McKinsey and Deloitte,
  quoted) — reliamag.com/guides/predictive-maintenance-roi-benchmarks-what-the-studies-show/

THESE ASSETS ARE ON MOBILE NETWORKS
- 73% of construction and heavy-equipment telematics is cellular — market.us/report/construction-heavy-equipment-telematics-market/
- NEOM's 5G network, built with stc — blooloop.com/technology/news/neom-stc-cognitive-cities-5g/

MARKET SIZING
- Global predictive maintenance, $14.6-15.1B — marketresearchfuture.com/reports/predictive-maintenance-market-2377,
  straitsresearch.com/report/predictive-maintenance-market, precedenceresearch.com/predictive-maintenance-market
- Smart ports, $4.0B to $39.1B by 2033 — grandviewresearch.com/industry-analysis/smart-port-market
- Saudi smart cities, $5.1B to $10.9B by 2030 — marketsandmarkets.com/Market-Reports/geography/smart-cities-market/saudi-arabia
- Maritime and port-equipment predictive maintenance, $1.22B to $2.87B by 2030 — market.us/report/predictive-maintenance-in-maritime-market/
- Port of NEOM Terminal 1, opening 2026 — neom.com/en-us/our-business/port-of-neom
- Automated cranes at Port of NEOM — arabnews.jp/en/business/article_148903/

ADJACENT PRODUCTS — characterisations of product category from public materials, not
benchmarks. We have run no comparison and quote no performance figures for any of them.
- c3.ai/products/applications/c3-ai-reliability
- siemens.com/en-us/company/artificial-intelligence/
- onomondo.com · ookla.com · esri.com

Footer line, set small: Vendor-published figures are labelled as such throughout. Where a
number originates with a research house we say so, and we say that we found it quoted in
a vendor write-up rather than in the primary report.
```
