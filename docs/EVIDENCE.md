# Is this a real problem, and is solving it worth it?

Sources for every claim in the pitch, plus the claims we deliberately do **not** make.

**On source quality.** Much of the field-service data comes from vendors who sell
solutions to the problem they are sizing, so their numbers deserve scepticism. Where a
figure originates with a research house — McKinsey, Deloitte, Aberdeen, Gartner — we say
so, and we flag that we found it quoted in a vendor's write-up rather than in the primary
report. Vendor-reported figures are labelled. Better to be caught being careful than
caught overstating.

---

## 1. The wasted dispatch is a named, measured, budgeted problem

Field service calls a dispatch a **truck roll**, and a trip where the technician finds
nothing wrong a **"no fault found" (NFF)** — the exact trip this system exists to prevent.

| Figure | Source |
|---|---|
| **$250–$600 per truck roll**, "in some cases, as high as $1,000" | [Automation Anywhere](https://www.automationanywhere.com/company/blog/rpa-thought-leadership/fixing-telecommunications-field-service) |
| **NFF rate of 17–20%** of all dispatches | [TechSee](https://techsee.com/blog/save-millions-lowering-no-fault-found-nff-dispatch-rate/) — *the vendor's own experience, not a third-party study; they note technicians under-report it* |
| **25% of service calls need at least one additional visit** | Aberdeen Group (2013), quoted in [Automation Anywhere](https://www.automationanywhere.com/company/blog/rpa-thought-leadership/fixing-telecommunications-field-service) |
| **75–85% first-visit completion** is common | [XOi](https://xoi.io/blog/truck-roll-optimization-field-service) — vendor |
| By 2025, **two-thirds of field service work** automatically scheduled by algorithms | Gartner, quoted in [Automation Anywhere](https://www.automationanywhere.com/company/blog/rpa-thought-leadership/fixing-telecommunications-field-service) — a *forecast* made for 2025, cited here in 2026; we have not verified whether it landed, so we use it as evidence that the industry expected this shift, not that it happened |

The worked example both sources use: an operator running **1,000 dispatches a day** over
252 working days at $250 each spends **$63 million a year** on field service — of which
**$10.7 million is NFF**, trips that resolved nothing.

**The honest caveat.** These figures come from *telecom consumer* field service — broadband
installs, set-top boxes — not heavy equipment. The mechanism is identical (dispatching to
something that turns out not to need it) and so is the cost structure, but the causes
differ: their NFF is cabling and resets, ours is coverage versus hardware. **We do not
claim a 17–20% NFF rate for construction fleets.** We claim the problem class is real,
measured, and already carries a budget line.

---

## 2. Downtime on construction equipment is expensive enough to justify the effort

| Figure | Source |
|---|---|
| **$3,200–$8,700 per machine per day** of unplanned downtime, all-in | [FleetRabbit](https://fleetrabbit.com/industry/construction-management-system/real-cost-construction-equipment-downtime) — vendor |
| Excavator loaded cost **$180–$340/hr**; one mid-project failure erases **$3,000–$6,000** of margin | [FleetRabbit](https://fleetrabbit.com/industry/construction-management-system/real-cost-construction-equipment-downtime) |
| A four-person crew idle at burdened rates costs **$340/hr** producing nothing | [FleetRabbit](https://fleetrabbit.com/industry/construction-management-system/real-cost-construction-equipment-downtime) |
| Liquidated-damages clauses of **$500–$5,000 per calendar day** for missed milestones | [FleetRabbit](https://fleetrabbit.com/industry/construction-management-system/real-cost-construction-equipment-downtime) |
| Unplanned downtime costs **3–5× more than planned** downtime | [For Construction Pros](https://www.forconstructionpros.com/equipment-management/article/21104195/the-true-cost-of-unplanned-equipment-downtime) |

A wasted trip is not the only cost. Every hour the wrong diagnosis delays the right repair
is another hour of idle crew and schedule risk.

---

## 3. Predicting failure early is established practice, with measured returns

| Figure | Source |
|---|---|
| **18–25% lower maintenance costs**; unplanned downtime cut **up to 50%** | McKinsey, quoted in [ReliaMag](https://reliamag.com/guides/predictive-maintenance-roi-benchmarks-what-the-studies-show/) |
| **Up to 40% lower maintenance cost**, **30–50% better reliability**, **50% less downtime** | Deloitte, quoted in [ReliaMag](https://reliamag.com/guides/predictive-maintenance-roi-benchmarks-what-the-studies-show/) |
| Proactive repairs cost **4–5× less** than emergency repairs on the same asset | [ReliaMag](https://reliamag.com/guides/predictive-maintenance-roi-benchmarks-what-the-studies-show/) |
| **95% of organisations** implementing predictive maintenance report positive ROI | [ReliaMag](https://reliamag.com/guides/predictive-maintenance-roi-benchmarks-what-the-studies-show/) |

Our contribution is not the idea of predicting failure — it is **warning time**. That result
holds inside a window, and the window is worth naming rather than leaving for a judge to
discover.

Measured on held-out machines — split by asset, never by row — against the baseline a fleet
actually runs today, an engine-temperature threshold:

| Time before failure | Our model | Engine-temp threshold |
|---|---|---|
| 0–24 h | **100%** | 31.4% |
| 24–48 h | **100%** | 19.9% |
| 48–72 h | **93.8%** | 19.6% |
| 72–96 h | 7.3% | *13.2%* |
| 96–120 h | 0% | *4.3%* |

Every cell comes from `detection_by_horizon` in [`ml/metrics.json`](../ml/metrics.json), which
is committed — 588–592 test windows per row.

**Inside three days we win decisively. Past three days we lose, and the reason is
structural.** `ml/train.py` trains one classifier per horizon at 24, 48 and 72 hours
(`HORIZON_H = 72.0`), while the run-to-failure ramp in `data/history_builder.py` lasts five
days (`DEGRADE_DAYS = 5.0`). No head was ever trained to warn earlier than three days out, so
the bottom two rows measure a model answering a question it was never asked at training time.
The fix is not subtle — train heads at 96 and 120 h — and it is work left undone rather than a
result we would rather you missed.

So the claim is bounded, and we state the bound: **within 72 hours of failure our model flags
93.8–100% of failures against a temperature threshold's 19.6–31.4%**, because vibration and
oil-particle trends move days before temperature does. Beyond 72 hours we make no claim at
all — the threshold is ahead. That comparison is ours, is measured on our own generated data,
and is reproducible from the repo.

---

## 4. These machines really are on mobile networks, and really do drop off them

| Figure | Source |
|---|---|
| **73.4%** of the construction and heavy-equipment telematics market is **cellular** | [Market.us](https://market.us/report/construction-heavy-equipment-telematics-market/) — market-research aggregator |
| Sites are *"inherently challenging from a connectivity perspective"*; cellular coverage *"where it exists, is often inconsistent"* | [Globalstar](https://www.globalstar.com/en-us/resource-center/articles/mining-enabling-visibility-safety-and-productivity) — vendor |
| Hybrid trackers exist specifically to fail over to satellite when cellular drops | [Trafalgar Wireless](https://trafalgarwireless.com/blog/satellite-iot-connectivity-for-asset-tracking/) |

An entire hardware category exists to work around coverage gaps on these sites. The
ambiguity we resolve is not hypothetical.

---

## 5. The target environment exists and is being built with an operator

| Figure | Source |
|---|---|
| NEOM contracted **STC to build its 5G network**, plus a bespoke **5G-Advanced** network | [blooloop](https://blooloop.com/technology/news/neom-stc-cognitive-cities-5g/), [Vision2030.ai](https://vision2030.ai/investment/zones/neom/) |
| NEOM is in *"active large-scale construction… with a workforce exceeding 200,000 on site"* | [Construction Week](https://www.constructionweekonline.com/news/saudi-gigaprojects-everything-you-need-to-know-about-neom) |

Our approach requires a site covered by an operator whose APIs can be queried. That is
precisely what NEOM is building.

---

## 6. The channels we model are the ones the industry actually instruments

The forecasting model reads vibration and oil-particle trends because those move days
before engine temperature does. That ordering is the product, so it is worth showing
these are real instrumentation practice rather than plausible-sounding channels we
invented to make the story work.

| Claim | Source |
|---|---|
| Vibration monitoring is standard condition monitoring on heavy equipment — accelerometers detect imbalance in bearings, gears and shafts, and the signature changes before failure | [Komatsu machine health monitoring](https://www.komatsu.com/en-us/services-and-support/joy-equipment-services/machine-health-monitoring) (vendor, labelled) |
| Post-2015 Cat and Komatsu machines broadcast hundreds of CAN-bus points over integrated telematics (Cat Connect / Product Link, KOMTRAX); vibration sensors are inexpensive | [Predictive maintenance for heavy equipment](https://heavyvehicleinspection.com/blog/post/predictive-maintenance-heavy-equipment-2026-guide) (vendor, labelled) |
| Oil analysis detects component wear from particles in the fluid, and is explicitly sold as trend analysis that finds problems "long before they materialize" | [Cat S·O·S Fluid Analysis](https://www.foleyeq.com/service/cat-service-technology/cat-sos-fluid-sampling/) (vendor, labelled) |
| Inline oil-debris sensors exist and are an active field — inductive, capacitive and optical methods — motivated precisely because offline lab sampling is slow and cannot reflect real-time oil status | [Impedance micro-sensor for metal debris monitoring of hydraulic oil](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7913635/) (peer-reviewed) |

**What this establishes and what it does not.** It establishes that vibration and oil
wear are genuinely the leading indicators maintenance engineers use, and that vibration
in particular already arrives as telemetry. It does not establish that a given fleet
streams oil-particle counts continuously — see the caveat below.

---

## 7. Adjacent products already exist. Here is where we actually sit.

Nobody should hear this pitch and think the space is empty. Several established companies
solve neighbouring parts of the problem, and a technical judge will know them by name.

| Company | Product category | Where it stops, for this problem |
|---|---|---|
| [Onomondo](https://onomondo.com/) | IoT cellular connectivity provider — its own SIMs, core network and device-level network diagnostics | Genuine connectivity truth, but through **one vendor's** network and SDK. A contractor running mixed fleets — subcontractors' machines on stc, Mobily and e& SIMs — needs an answer that does not depend on whose SIM is in the machine. |
| [Ookla](https://www.ookla.com/) | Network measurement and coverage analytics (Speedtest; operator-facing coverage and cell analytics) | Tells you what coverage looks like, as measurement and reporting. It is not a per-device, per-incident verdict that something downstream acts on. |
| [Esri](https://www.esri.com/) | ArcGIS — the geospatial platform much field-asset, mapping and dispatch tooling is built on | Renders the site and the fleet superbly. The decision about whether to roll a truck is still a human reading the map. |

*These are characterisations of product category taken from the companies' public materials —
not benchmarks. We have not run a comparison against any of them and we quote no performance
figures for them. Read the right-hand column as our positioning argument, not as a measured
finding.*

Our angle is the **combination** of three properties, not any one of them alone:

1. **Carrier-agnostic.** We call GSMA Open Gateway / CAMARA standard endpoints, not a single
   vendor's SDK. The same Device Status call is meant to work against whichever operator holds
   the SIM — which is the only shape that survives a giga-project's mixed subcontractor fleet.
   (With the caveat already listed below: each operator relationship is real plumbing.)
2. **Autonomous decisioning, not a dashboard.** The network answer is consumed by an agent
   that decides, not painted onto a screen for a human to notice. Our dashboard exists so a
   judge can watch the reasoning; the loop does not need it to run.
3. **The loop closes on a part, not an alert.** The output is a work order naming a component
   with a technician routed to network-verified coordinates — not a red row someone triages.

Put plainly: **we apply standardised operator APIs to a problem solved today with vendor
lock-in and manual triage.** The claim is not that nobody does this. It is that the seam
between connectivity truth, failure prediction and dispatch is currently crossed by hand, and
that standard APIs are what make crossing it automatically portable across operators.

---

## What this is worth on a giga-project fleet

**Illustrative arithmetic, not a measurement.** Written out so the assumptions are visible
and arguable rather than hidden inside a headline number.

Take a 500-machine fleet — the size of our dataset — where each machine raises one
"went silent" alert a month:

- 500 alerts/month
- × roughly **20%** that turn out to be connectivity rather than hardware *(industry NFF analogue — our assumption, and the weakest link here)*
- ≈ **100 avoidable dispatches/month**
- × **$250–$1,000** per truck roll
- = **$25,000–$100,000/month**, or roughly **$300k–$1.2M/year** in trips never taken

Separately, on the downtime side: catching a failure days early rather than hours turns an
emergency repair into a planned one — **4–5× cheaper on the same asset** — against a
backdrop of **$3,200–$8,700 per machine per day** when a machine stops unexpectedly.

Every input above is someone else's published figure except the alert rate, which is ours
and is stated rather than buried.

---

## What we do NOT claim

- **The 40% / 25% / 15% headline figures are targets, not measurements.** We have not run
  this on a real fleet.
- **The 17–20% NFF rate is telecom, not construction.** We use it to show the problem class
  is real and budgeted, not to size our own impact.
- **Numbers computed from our own datasets describe the system's behaviour, not the world.**
  Both generators are in the repo; anything derived from them is a property of choices we
  made. The 93.8%-versus-19.6% warning-time result at 48–72 h is our model on our data.
- **The warning-time claim is bounded at 72 hours and we do not stretch it.** Past 72 h the
  temperature threshold beats us (7.3% vs 13.2% at 72–96 h; 0% vs 4.3% at 96–120 h), because
  no model head was trained beyond 72 h. Both directions are in §3, and every horizon —
  including the two we lose — is in `ml/metrics.json`, which is committed and reproducible.
  Where the pitch quotes the 48–72 h number on its own, it is quoting the bound stated here,
  not a claim that the advantage continues past it.
- **We do not claim nobody else does this.** Onomondo, Ookla and Esri, among others, hold
  adjacent ground (§7). Our positioning against them is an argument about carrier-agnosticism,
  autonomy and loop closure — not a benchmark, and not a claim of an empty market.
- **Not every remote asset is cellular.** Some sites run satellite or private LoRaWAN, where
  this approach does not apply. Giga-projects built with a national operator are where it does.
- **Querying a SIM's status needs a commercial relationship with the operator holding it.**
  Straightforward, but real plumbing for a contractor running mixed fleets across carriers.
- **Oil-particle counts are not usually a live feed.** Vibration is standard telemetry
  today; oil condition on heavy equipment is predominantly *scheduled sampling* — a
  technician draws a sample and the lab turns it round in about 24 hours ([Cat
  S·O·S](https://www.foleyeq.com/service/cat-service-technology/cat-sos-fluid-sampling/)).
  Inline debris sensors exist and are getting cheaper, but they are not standard fitment
  the way engine ECU data is. We model both channels as continuous because the signal the
  model needs is a multi-day trend, which sampling supplies anyway at lower resolution —
  but on a real fleet today the two channels would arrive at different cadences, and the
  ingestion layer would have to carry that.
- **Several sources above are vendors sizing a problem they sell into.** They are labelled,
  and we lean on the research-house figures where they exist.
