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
| By 2025, **two-thirds of field service work** automatically scheduled by algorithms | Gartner, quoted in [Automation Anywhere](https://www.automationanywhere.com/company/blog/rpa-thought-leadership/fixing-telecommunications-field-service) |

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

Our contribution is not the idea of predicting failure — it is **warning time**. Measured
on held-out machines, at two to three days out our model flags **94%** of failures where an
engine-temperature threshold flags **2%**, because vibration and oil-particle trends move
days before temperature does. That comparison is ours and is reproducible from the repo.

---

## 4. These machines really are on mobile networks, and really do drop off them

| Figure | Source |
|---|---|
| **73.4%** of the construction and heavy-equipment telematics market is **cellular** | [Market.us](https://market.us/report/construction-heavy-equipment-telematics-market/) |
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
  made. The 94%-versus-2% warning-time result is our model on our data.
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
