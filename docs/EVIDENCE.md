# Is this a real problem?

Sources for the claims in the pitch, so nothing rests on assertion. Figures published
by vendors are marked as such — they have an interest in the number being large.

---

## 1. A wasted dispatch is expensive, and it is measured

The field-service industry has a name for this: a **truck roll**.

- **$150–$500 in direct cost** per truck roll, with industry estimates putting the true
  figure near **$1,000** once labour, fuel, vehicle wear and overhead are counted.
  ([vSight](https://vsight.io/glossary/what-is-a-truck-roll/),
  [Blitzz](https://blitzz.co/blog/the-real-cost-of-a-truck-roll-and-how-to-avoid-it))
- The industry tracks **"no fault found" (NFF)** dispatches as their own category —
  trips where the technician arrives and there is nothing to repair. This is precisely
  the failure mode this system exists to prevent.
- **First-visit completion rate** is the standard metric. Operators on modern platforms
  reach 90%+; **many sit at 75–85%**, meaning one visit in four to five does not resolve
  the problem. ([XOi](https://xoi.io/blog/truck-roll-optimization-field-service))

**Why this matters for us:** the problem is not our framing. It is a named, measured,
budgeted line item in field service, and "no fault found" is already the term of art for
the exact trip our agent prevents.

---

## 2. Remote industrial sites genuinely lose connectivity

- Mining and heavy-construction sites are *"inherently challenging from a connectivity
  perspective, with equipment constantly moving across changing terrain, new zones being
  opened while others are decommissioned, and temporary infrastructure being common."*
  Cellular coverage *"where it exists, is often inconsistent."*
  ([Globalstar](https://www.globalstar.com/en-us/resource-center/articles/mining-enabling-visibility-safety-and-productivity))
- **Cellular is how this equipment reports: 73.4% of the construction and heavy-equipment
  telematics market.** So the machines really are on mobile networks, and really do drop
  off them. ([Market.us](https://market.us/report/construction-heavy-equipment-telematics-market/))
- Hybrid trackers exist specifically to fail over to satellite when cellular drops —
  an entire product category built around the premise that coverage gaps are routine.

**Why this matters for us:** the ambiguity we resolve is real. A machine on a giga-site
goes quiet for connectivity reasons often enough that the industry sells hardware to work
around it.

---

## 3. Downtime on these sites is costly enough to justify the effort

- Large mining operations put unplanned downtime at **$130,000–$187,000 per hour**, with
  a four-hour outage exceeding **$500,000**.
  ([Globalstar](https://www.globalstar.com/en-us/resource-center/articles/mining-enabling-visibility-safety-and-productivity))

Construction is not mining, and we should not quote mining figures as if they were ours.
The point that transfers is the shape of the economics: on assets this large, hours of
avoidable downtime dominate the cost of the monitoring that prevents them.

---

## 4. The target sites are real, connected, and under construction now

- NEOM contracted **STC to build its 5G network**, with a bespoke **5G-Advanced** network
  planned alongside fibre and IoT infrastructure.
  ([blooloop](https://blooloop.com/technology/news/neom-stc-cognitive-cities-5g/),
  [Vision2030.ai](https://vision2030.ai/investment/zones/neom/))
- NEOM has *"transitioned from the conceptual phase into active large-scale construction,
  with billions of dollars in contracts awarded and a workforce exceeding 200,000 on
  site."* ([Construction Week](https://www.constructionweekonline.com/news/saudi-gigaprojects-everything-you-need-to-know-about-neom))

**Why this matters for us:** the environment we designed for exists, is being built now,
and is being built *with a mobile operator*. Our approach depends on the site being
covered by a network whose APIs can be queried — which is exactly what NEOM is
constructing with STC.

---

## What we do NOT claim

- **The 40% / 25% / 15% figures in the deck are targets, not measurements.** We have not
  run this on a real fleet.
- **Numbers computed from our own datasets describe the system's behaviour, not the
  world.** Both generators are in the repo; anything derived from them is a property of
  choices we made.
- **Not every remote asset is cellular.** Some sites use satellite or private LoRaWAN,
  where the CAMARA approach does not apply. Giga-projects being built with a national
  operator are the environment where it does.
- **Querying a SIM's status requires a commercial relationship with the operator holding
  it.** Straightforward, but real plumbing for a contractor running mixed fleets across
  several carriers.
