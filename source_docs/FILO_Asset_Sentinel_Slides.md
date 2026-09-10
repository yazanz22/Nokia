# FILO Asset Sentinel — Market Validation Slides

## Table of Contents
1. [Slide 1 — The Problem & Market Opportunity](#slide-1--the-problem--market-opportunity)
2. [Slide 2 — Who Pays For This](#slide-2--who-pays-for-this)
3. [Slide 3 — Economic ROI](#slide-3--economic-roi)
4. [Slide 4 — What We're Validating Next](#slide-4--what-were-validating-next)
5. [Backup Slide — References](#backup-slide--references)

---

## Slide 1 — The Problem & Market Opportunity

**One-liner:**
> When a NEOM-scale asset goes silent, operators can't tell hardware failure from network dropout — so they default to a 2-hour dispatch that's wrong ~49% of the time.

**Bottom-up market sizing funnel:**
- **TAM** — Global Predictive Maintenance market: $14.6–15.1B (2025)
- **SAM** — Smart Ports ($4.0B → $39.1B by 2033) + Saudi Smart Cities ($5.1B → $10.9B by 2030) + Maritime PdM ($1.22B → $2.87B by 2030)
- **SOM** — Pilot-sized: one division/terminal (e.g., Oxagon), low-single-digit millions in year 1

**Footnote:** 51/49 hardware/network split and dispatch-cost figures are internal fleet data — currently being customer-validated.

---

## Slide 2 — Who Pays For This

- **Primary ICP:** NEOM giga-project operators, Port of NEOM (Terminal 1, 2026 launch)
- **Buyer:** field ops manager / maintenance supervisor / IT lead — not the organization as a whole
- **Adjacent segments with the same problem:**
  - Oil & gas — remote assets, coverage gaps, high dispatch cost
  - Mining — same telemetry ambiguity, harsher terrain
  - Utilities — distributed grid assets, SLA penalties on downtime
  - Logistics — fleet-wide connectivity dropouts
- **Differentiation vs. C3 AI / Siemens / traditional SCADA:** network-level truth via CAMARA, not on-board sensors alone

---

## Slide 3 — Economic ROI

- **Cost per incorrect dispatch:** $150/hr × 4hr ≈ $600 *(placeholder — needs real site rates)*
- **Savings model:** at a 49% false-positive rate on 100 alerts/month → ~49 avoided dispatches/month → ~$29K/month, ~$350K/year saved (illustrative 1,000-asset fleet)
- **Payback period:** ~7–14 months against $50–100K implementation cost
- **Secondary lift:** single-visit resolution from corrective + predictive maintenance overlap

---

## Slide 4 — What We're Validating Next

| Claim | Status | How We'll Validate |
|---|---|---|
| 51/49 hardware/network split | Unvalidated | Customer interviews on past dispatch outcomes |
| $/dispatch cost | Placeholder | Pull real technician/vehicle rates from a target site |
| Willingness to change dispatch workflow | Unvalidated | Mom Test–style interviews — ask about their history, not their opinion of our product |

**Ask:** Propose a pilot at one NEOM division or Port of NEOM terminal to generate real numbers.

---

## Backup Slide — References

### Slide 1 sources
- Global PdM market size: https://www.marketresearchfuture.com/reports/predictive-maintenance-market-2377
- Global PdM market size (alt): https://straitsresearch.com/report/predictive-maintenance-market
- Global PdM market size (alt): https://www.precedenceresearch.com/predictive-maintenance-market
- Smart Ports market: https://www.grandviewresearch.com/industry-analysis/smart-port-market
- Saudi Smart Cities market: https://www.marketsandmarkets.com/Market-Reports/geography/smart-cities-market/saudi-arabia
- Maritime PdM market: https://finance.yahoo.com/sectors/technology/articles/port-equipment-predictive-maintenance-global-080400128.html
- Maritime PdM market (alt): https://natlawreview.com/press-releases/port-equipment-predictive-maintenance-market-hit-287-billion-2030-reports
- Maritime PdM market (alt): https://market.us/report/predictive-maintenance-in-maritime-market/
- Ports & Terminal Operations market: https://www.technavio.com/report/ports-and-terminal-operations-market-industry-analysis

### Slide 2 sources
- Port of NEOM overview: https://www.neom.com/en-us/our-business/port-of-neom
- Terminal 1 / 2026 launch: https://saudilogisticsconsulting.com/insights/articles/port-of-neom-terminal-1-opens-in-2026-port-of-neom-2026-launch-and-a-new-era-for-saudi-container-logistics
- Automated cranes at Port of NEOM: https://www.arabnews.jp/en/business/article_148903/
- NEOM giga-project scale: https://vision2030.ai/encyclopedia/neom/
- NEOM giga-project investment (PIF): https://www.pif.gov.sa/en/our-investments/giga-projects/
- NEOM giga-project status: https://saudimarketresearchconsulting.com/insights/articles/the-giga-project-scorecard-saudi-arabia-giga-projects-status-mid-2026-whats-real-now
- Competitor — C3 AI Reliability: https://c3.ai/products/applications/c3-ai-reliability
- Competitor — C3 AI + Shell partnership: https://www.businesswire.com/news/home/20231011779354/en/C3-AI-and-Shell-Expand-Collaboration-for-Asset-Monitoring-and-Predictive-Maintenance
- Competitor — SensFlo vs. C3.ai: https://www.sensflo.ai/articles/sensflo-vs-c3
- Competitor — Siemens industrial AI: https://www.siemens.com/en-us/company/artificial-intelligence/

### Slide 3 sources
- Industrial downtime cost (~$1T/yr): https://iot-analytics.com/1-trillion-industrial-downtime-problem-is-becoming-a-knowledge-problem/
- PdM ROI benchmarks (200–500% yr 1): https://ifactoryapp.com/predictive-maintenance/roi-turnkey-ai-predictive-maintenance-real-numbers-deployments
- PdM cost savings (18–25%, downtime cut 30–50%): https://wiss.com/predictive-maintenance-roi-cost-savings-for-manufacturers/
- IoT sensor cost drop ($600 → $50/point): https://oxmaint.com/article/iot-sensors-predictive-maintenance-guide
- False-positive reduction via AI filtering: https://ifactoryapp.com/predictive-maintenance/role-of-iot-in-predictive-maintenance-real-time-data
- Field dispatch inefficiency: https://www.genicteams.com/how-poor-dispatching-quietly-erodes-field-service-profitability/
- Logistics dispatch case study (200-truck fleet): https://flogesoft.com/proof/logistics-ops.html

### Slide 4 sources
- IIoT projects failing to solve a clear problem: https://www.l2l.com/blog/5-reasons-industrial-iot-fails
- Port of NEOM existing pilot precedent (Egypt/Iraq transit): https://www.logisticsmiddleeast.com/logistics/port-of-neom-pilot-halves-transit-times-across-egypt-saudi-arabia-and-iraq
- Oxagon $1B port contract precedent: https://www.linkedin.com/pulse/neom-awards-estimated-1bn-oxagon-port-contract-meed-er9cf
- Port automation cost of delay ($6.9B demurrage/detention): https://www.marineinsight.com/the-6-9-billion-cost-of-non-automated-port-operations-why-delays-are-becoming-more-expensive/
