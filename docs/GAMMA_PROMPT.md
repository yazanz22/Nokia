# Gamma AI prompts — FILO Asset Sentinel pitch deck

**14 cards**, generated in two passes because Gamma's free tier caps a generation at 10:
**Deck A (10 cards)** and **Deck B (4 cards)**.

Rewritten 2026-09-10. The previous version ran to 17 cards, was roughly nine-tenths
technical, and spent a good deal of its own slide space arguing against itself. This one
splits about evenly between how it works and what it is worth, and the caveats live in
`docs/EVIDENCE.md` rather than on the slide face. Earlier versions are in git history.

## How to run this

1. In Gamma: **Create new → Paste in text**, paste **Prompt A**, set card count to **10**, generate.
2. **Note the theme Gamma applied** (the theme name is in the editor's side panel).
3. New generation: **Paste in text**, paste **Prompt B**, set card count to **4**, and — before
   generating — **pick the same theme by name**. Theme selection is a UI action; no prompt can do
   it for you, and it is the single thing most likely to make the seam visible.
4. Combine: in Deck A, use **Add card → Import / duplicate from another deck**, or export both to
   PowerPoint and paste Deck B's four slides after Deck A's ten.

The two style blocks below are **deliberately identical, word for word**. Don't edit one without
editing the other — that's what keeps the halves looking like one deck.

## Keeping the cards the same size

Cards in the previous deck ran from 42 to 364 words — a **7.8× spread** — and Gamma sizes a
card to fit its content, so the long ones overflowed and scrolled while the short ones sat
half empty. Two things fix it, and the first matters far more:

- **The card blocks below are written to an even word budget.** Every content card lands
  between 76 and 128 words — a 1.7x spread, against 7.8x before. The title card is
  naturally shorter and the sources card is a reference list rather than prose; those two
  aside, keep any edit inside that band. It is the actual lever.
- In Gamma, set **Card dimensions** to a fixed size (side panel, under the theme) rather than
  letting it auto-fit, and check each card at presentation size before exporting.

If a card still overflows, cut words from that card — do not shrink the type, which breaks the
visual match with the other half of the deck.

## Checks after generating

- Deck A must **not** end with a "thank you" or summary card — card 10 is the last one.
- Deck B must **not** start with a title or cover card — its card 1 is content.
- Gamma rounds numbers. Confirm **92.2%**, **88.6%**, **$278k**, **$1.66M** and **$11.10M**
  survived intact.
- **No card should need scrolling at presentation size.** Check every one.
- Deck A cards 4, 5, 6 and 7 must be visual — a flow, a table, a grouped list and a layered
  diagram. If one came out as a plain paragraph, regenerate that card.
- Deck A card 6 must name **all five** network signals. Gamma likes to compress it to two
  (reachability + location) and drop roaming — which is the one signal nothing else can see,
  and the one card 5's roaming row depends on.
- Deck B card 4 is the sources card, and its whole value is that every entry is real. Check
  each link against the prompt rather than skimming: a generator that shortens a URL, "tidies"
  a domain or invents a plausible-looking one has produced a citation to nothing. Confirm the
  count too — if fewer entries came out than went in, it merged some.
- **Theme match is not automatic — confirmed by an actual combine on 2026-09-03.** Two separate
  generations produced two visually unrelated decks (a light minimal sans-serif for A, a bold
  black condensed display face for B) even from the same style block. Picking the same theme by
  name in step 3 is not optional polish; skip it and the combined deck reads as two decks
  stapled together.
- **Gamma invents specific factual claims when a card has room, not just numbers — confirmed.**
  On an earlier impact card it added "NEOM and Masdar City are required to report Scope 3
  emissions on major projects" — a specific regulatory claim with no source anywhere in the
  prompt. It also computed a ratio of its own and printed it as "47× more impending failures",
  a figure it was never given. Read every card's added sentences, not just its numbers — a
  plausible-sounding claim that was never supplied is a fabrication regardless of whether a
  number changed.
- Gamma likes to add a hockey-stick "Year 1 / Year 3 / Year 5" revenue row to market and
  pricing cards. We have no such forecast; anything it adds there is invented. Delete it.
- On a diagram slide, check reading order against the slide's own caption. A pyramid is
  conventionally read foundation-at-base — Layer 1 wide at the bottom is *correct*. A numbered
  step sequence is not: if the caption says "from X to Y," X must be first in reading order.
  Both patterns were confirmed wrong in the same generated deck.

## Where each figure comes from

**Repo-traceable — verified against the source of truth in this repository:**
`ml/metrics.json` (92.2%, 88.6%, and the perfect network-class separation on held-out data),
`docs/EVIDENCE.md` (every sourced cost figure and the savings model), `data/dataset1.csv`.
The savings tiers on Deck B card 1 are `EVIDENCE.md`'s midpoint case at an 80% capture rate,
recomputed and checked row by row.

**Third-party market sizing — checked against the source pages on 2026-09-12**, after the
draft in `source_docs/` was found to carry three figures its own citations did not support.
What the pages say now:

| Figure | Source | Status |
|---|---|---|
| Saudi smart cities $5.1B (2025) → $10.9B (2030) | MarketsandMarkets | Verified exactly |
| Port-equipment PdM $1.22B (2025) → $2.87B (2030) | natlawreview press release | Verified; note it is a press release, not a research house report |
| Global PdM $14.6B (2025) | Straits Research | Verified |
| Smart ports $4.0B → $39.1B by 2033 | Grand View Research | **Still unverified** — the page returns 403 to automated fetches. Open it by hand before submitting |

Three corrections were made rather than carried forward, and the reasons are worth keeping:

- The draft gave the TAM as a **$14.6–15.1B range across three research houses**. Straits says
  $14.63B and Market Research Future's header says $15.10B, but MRF's own summary on the same
  page says $43.88B, and Precedence says **$9.21B**. The "range" was two agreeing numbers with
  a contradicting source cited beside them. It is now a single figure attributed to Straits,
  and the other two URLs are off the sources card.
- The draft labelled a line "maritime and port-equipment predictive maintenance" and cited
  market.us's *Predictive Maintenance in Maritime* report. That report says $433M (2024) →
  $3,058M (2034). The $1.22B → $2.87B figures belong to a different market, Port Equipment
  Predictive Maintenance. The label and the citation now match the numbers.
- Market sizes for the same named market differ by 4x between research houses, which is normal
  and is why each figure now carries the house that produced it.

---

# PROMPT A — cards 1–10

```
You are helping build a pitch deck for a hackathon judging panel. Create a 10-card
presentation from the content below. This is the FIRST HALF of a longer deck; four more
cards will be appended afterwards.

STYLE
- Audience: telecom and enterprise judges at the GSMA MENA Ignite / MENA Open Gateway
  Hackathon. Technical, senior, commercially literate.
- Tone: confident, concrete, declarative. Engineering credibility over marketing energy.
  State what the system does and what it is worth. Do not hedge, qualify, or argue
  against the product.
- Visual direction: dark industrial theme. Desert dusk palette — deep charcoal and slate
  backgrounds, high-visibility amber as the single accent colour, one cool teal for
  "healthy" states. Condensed sans-serif headings, monospace for any data, metrics or
  code. Think industrial telemetry console, not SaaS landing page.
- Imagery: unattended industrial plant in desert and port terrain — generators, pump
  sets, compressors, light towers standing alone; cellular coverage abstractions;
  telemetry dashboards. No stock photos of people in hard hats pointing at tablets. No
  generic "AI brain" or glowing-circuit imagery.
- Layout: prefer diagrams, tables and metric callouts over bullet lists.

RULES — IMPORTANT
- Use ONLY the facts and numbers given below. Do not invent, extrapolate or "round up"
  any statistic, and do not add a revenue forecast or growth projection — none exists.
- SIZING: every card must fit one screen with no scrolling. The blocks below are written
  to an even length on purpose. Do not expand a card that looks short — if a card needs
  more presence, make it more visual, not longer.
- Produce exactly 10 cards, one per CARD block below. Do not merge or split them.
- Do NOT add a closing, summary or thank-you card. The deck continues after card 10.
- Cards 4, 5, 6 and 7 must be visual: a flow diagram, a table, a grouped list and a
  layered diagram respectively.
- Add speaker notes to each card expanding on the argument for a live pitch.

---

CARD 1 — TITLE
FILO Asset Sentinel
Autonomous diagnostics for unattended industrial assets
Team FILO · Theme 2: Smart Cities, Urban Safety & Mega-Project Infrastructure
Built on CAMARA network APIs via Nokia Network as Code

CARD 2 — ONE PROBLEM
A silent asset cannot tell you why it is silent.
Generators, pump sets, compressors, light towers — plant that runs unattended, overnight
and between shifts, with nobody on it to report anything.
When one stops transmitting, the data that would explain the silence is exactly the data
that stopped arriving. A seized engine, a failed sensor and a cellular dead zone are the
same event from the operations centre: nothing.
So somebody drives out to find out. That guess is the problem, and everything we built
exists to remove it.

CARD 3 — WHAT THE GUESS COSTS
- $250–$600 per truck roll, and up to $1,000. (Automation Anywhere)
- 17–20% of telecom field-service dispatches find nothing wrong. (TechSee)
- $3,200–$8,700 per machine per day of unplanned downtime. (FleetRabbit)
- 25% of service calls need a second visit — the first technician arrived without the
  right part. (Aberdeen Group)
- 73% of heavy-equipment telematics runs over cellular, so coverage is a live variable.
  (Market.us)
At giga-project scale — hundreds of assets across thousands of square kilometres — that
guesswork compounds into schedule, budget and crew-safety risk.

CARD 4 — THE NETWORK IS THE MISSING WITNESS (make this a horizontal flow diagram)
If the machine cannot tell you why it went quiet, ask the network that was carrying it.
The operator knows whether that SIM is still attached, what its last signal was, whether
neighbouring cells were failing, and whether it has roamed abroad. No on-board sensor
produces any of it — the device is dark.
Flow: Heartbeat lost → Query CAMARA Device Reachability → Weigh signal, neighbour cells,
roaming country → Verdict → No dispatch, or a graded dispatch carrying the right part
Caption: The agent runs this on its own, in seconds, before anyone is asked to drive
anywhere.

CARD 5 — FIVE OUTCOMES, TWO GRADED DISPATCHES (make this a table)
Columns: Situation | Network evidence | Action
- Coverage gap | Unreachable, weak last signal, neighbour-cell failures | Log blind spot,
  automatic re-check — NO DISPATCH
- Roamed across the border | Attached to a Jordanian network | Connectivity ticket — NO
  DISPATCH
- Transient dropout | Reachable, telemetry nominal | Re-check — NO DISPATCH
- Sensor fault | Machine healthy, telemetry channel dead | Low-cost sensor kit
- Hardware fault | No network cause found | ML names the component, dispatch with the part
Caption: Three of the five outcomes send nobody. NEOM sits kilometres from Egyptian and
Jordanian networks — border roaming is a real event here, and invisible to every on-board
sensor.

CARD 6 — FIVE NETWORK SIGNALS, FOUR CAMARA FAMILIES (make this a grouped list, one line each)
- Device Reachability Status — the truth layer. Is this device still on the network?
- Device Roaming Status — the signal nothing else can see. A machine can be healthy,
  attached and still silent, because it attached to somebody else's network.
- Congestion Insights — survives a dark device. Grades the serving area when the device
  itself can no longer answer.
- Geofencing Subscriptions — the network pushes to us, warning while the asset is still
  healthy, before it crosses into foreign coverage.
- Location Retrieval — used twice: the silent machine's true position, and which
  technician is genuinely nearest right now.
All via Nokia Network as Code, GSMA Open Gateway compliant — carrier-portable, not locked
to a single telematics vendor.

CARD 7 — ARCHITECTURE (make this a layered diagram, four layers)
1. Telemetry ingestion — CAN-bus, engine temperature, vibration, battery voltage, GPS
2. AI agent orchestration — autonomous triage; the agent chooses which tools to call and
   in what order, and learns the site: every resolution is recorded against a ~2 km cell,
   so a repeat coverage failure becomes a known dead zone
3. Network as Code — four CAMARA families, five signals
4. Action — work-order generation, technician routing, live operations dashboard
Caption: The agent decides which evidence to gather. Every terminal action is a tool with
fixed logic that re-derives the verdict independently before it will act — autonomy where
it adds judgement, determinism where it would add risk.

CARD 8 — THE MACHINE LEARNING (three prominent stat callouts)
- 92.2% — failures caught 48–72 hours ahead, against 19.6% for the engine-temperature
  threshold fleets alarm on today. Vibration and oil-particle trends move days before
  temperature does.
- 88.6% — component classifier accuracy, 0.872 macro F1, across four components. This is
  what turns a work order from "go and look at it" into "bring this part".
- Zero — false dispatches for coverage gaps on held-out test data. On our test set the
  agent separates network-caused silence from hardware failure perfectly.

CARD 9 — THE MARKET (make this a TAM → SAM → SOM funnel diagram)
- TAM — global predictive maintenance: $14.6B in 2025 (Straits Research)
- SAM — unattended assets on operator networks in our region: smart ports ($4.0B, forecast
  $39.1B by 2033) + Saudi smart cities ($5.1B in 2025, forecast $10.9B by 2030) +
  port-equipment predictive maintenance ($1.22B in 2025, forecast $2.87B by 2030)
- SOM — one division or one terminal: pilot-sized, low single-digit millions in year one
Ports are the same product, not a pivot: a container terminal runs the same unattended
plant on the same operator networks, with the same ambiguity when one goes quiet. Port of
NEOM Terminal 1 opens in 2026 with automated cranes.

CARD 10 — WHO PAYS
Primary customers: giga-project and terminal operators — NEOM, Port of NEOM, Red Sea
Global, Qiddiya, Masdar City, Msheireb Doha — plus main contractors and heavy-equipment
rental fleets across the same corridor.
The buyer is a person: the field operations manager who owns the dispatch budget.
Where we sit against what already exists:
- C3 AI, Siemens, SCADA — predictive maintenance from on-board sensors. Strong at "this
  asset is degrading". A silent asset has stopped feeding them.
- Onomondo — network-level diagnostics, through one vendor's SIMs. Giga-projects run
  subcontractor fleets across stc, Mobily and e&.
- Esri, Ookla — render the site, measure the coverage. A human still decides.
```

---

# PROMPT B — cards 11–14

```
You are helping build a pitch deck for a hackathon judging panel. Create a 4-card
presentation from the content below.

CRITICAL: these cards are the SECOND HALF of an existing deck and will be appended
directly after it. Do NOT create a title card, cover card, agenda card or introduction.
Card 1 below is a content card and must be the first card you produce. The audience has
already seen the problem, the architecture, the API design and the market — do not
re-introduce the product or re-explain what it does.

STYLE
- Audience: telecom and enterprise judges at the GSMA MENA Ignite / MENA Open Gateway
  Hackathon. Technical, senior, commercially literate.
- Tone: confident, concrete, declarative. Engineering credibility over marketing energy.
  State what the system does and what it is worth. Do not hedge, qualify, or argue
  against the product.
- Visual direction: dark industrial theme. Desert dusk palette — deep charcoal and slate
  backgrounds, high-visibility amber as the single accent colour, one cool teal for
  "healthy" states. Condensed sans-serif headings, monospace for any data, metrics or
  code. Think industrial telemetry console, not SaaS landing page.
- Imagery: unattended industrial plant in desert and port terrain — generators, pump
  sets, compressors, light towers standing alone; cellular coverage abstractions;
  telemetry dashboards. No stock photos of people in hard hats pointing at tablets. No
  generic "AI brain" or glowing-circuit imagery.
- Layout: prefer diagrams, tables and metric callouts over bullet lists.

RULES — IMPORTANT
- Use ONLY the facts and numbers given below. Do not invent, extrapolate or "round up"
  any statistic, and do not add a revenue forecast, growth curve or year-by-year table —
  none exists.
- SIZING: every card must fit one screen with no scrolling. Card 4 is a dense reference
  list and should be set in small type, multi-column.
- Produce exactly 4 cards, one per CARD block below. Do not merge or split them.
- Card 1 must be a table with the three fleet tiers as rows, savings emphasised.
- Add speaker notes to each card expanding on the argument for a live pitch.

---

CARD 1 — WHAT IT SAVES (make this a table, three rows, savings column emphasised)
Projected annual saving on avoided dispatches, by fleet size.
Columns: Fleet | Field crew | Wasted dispatch spend | Projected saving
- Small | 5 technicians | $347k | $278k
- Mid-sized | 30 technicians | $2.08M | $1.66M
- Large | 200 technicians | $13.87M | $11.10M
Modelled on published field-service rates: 3.5 dispatches per technician per day, 252
working days, 18.5% finding nothing wrong, $425 per roll, 80% of those caught before
anyone drives.
On top of that: catching a failure early turns an emergency repair into a planned one, and
unplanned work costs 3–5× planned. One avoided downtime day is worth $3,200–$8,700.

CARD 2 — BUSINESS MODEL
Priced per connected asset per month. A 500-asset fleet at $30 per asset per month pays
$180k a year against $1.66M of projected saving — a 9× return on avoided dispatches alone,
before a single downtime day is counted.
Two revenue streams:
- Tiered SaaS subscription per asset per month, scaling with fleet size and site expansion
- Value-based API premium on automated decision volume — customers pay in proportion to
  the dispatches avoided
Cloud-native and serverless on pay-per-use telecom APIs: infrastructure scales with
demand, not ahead of it.
Why it travels: built on GSMA Open Gateway rather than one vendor's telematics stack, so
the same integration works across operators and across markets — ports, factories, oil and
gas, mining, utilities. Same unattended plant, same ambiguity, same answer.

CARD 3 — TEAM FILO AND THE ASK
Yazan Zarka — Software Engineer. Backend systems and CAMARA API integration.
Faris Alshafie — Software Engineer. Cloud architecture and the operations dashboard.
Yazan Abed — Data Scientist. Predictive maintenance modelling and anomaly detection.
Omar Hawasheen — Data Scientist. AI agent orchestration and decision logic.
The ask: one pilot, at one NEOM division or one Port of NEOM terminal.
Closing line, displayed prominently: You cannot diagnose a silent machine from the
machine. So we asked the network.

CARD 4 — SOURCES
Reference card. Small type, multi-column, no imagery. Title it "Sources". Keep every URL
exactly as written.

OUR MEASUREMENTS — reproducible at github.com/yazanz22/Nokia
ml/metrics.json (model results) · data/dataset1.csv (the dataset) · docs/EVIDENCE.md
(every sourced figure)

DISPATCH AND DOWNTIME COST
automationanywhere.com/company/blog/rpa-thought-leadership/fixing-telecommunications-field-service
techsee.com/blog/save-millions-lowering-no-fault-found-nff-dispatch-rate/
smarty.com/articles/truck-roll-costs
fleetrabbit.com/industry/construction-management-system/real-cost-construction-equipment-downtime
forconstructionpros.com/equipment-management/article/21104195/the-true-cost-of-unplanned-equipment-downtime
reliamag.com/guides/predictive-maintenance-roi-benchmarks-what-the-studies-show/

ASSETS ON MOBILE NETWORKS
market.us/report/construction-heavy-equipment-telematics-market/
blooloop.com/technology/news/neom-stc-cognitive-cities-5g/

MARKET SIZING
straitsresearch.com/report/predictive-maintenance-market
grandviewresearch.com/industry-analysis/smart-port-market
marketsandmarkets.com/Market-Reports/geography/smart-cities-market/saudi-arabia
natlawreview.com/press-releases/port-equipment-predictive-maintenance-market-hit-287-billion-2030-reports
neom.com/en-us/our-business/port-of-neom
arabnews.jp/en/business/article_148903/

ADJACENT PRODUCTS
c3.ai/products/applications/c3-ai-reliability · siemens.com/en-us/company/artificial-intelligence/
onomondo.com · ookla.com · esri.com
```
