# CLAUDE.md — MENA Open Gateway Hackathon / Team FILO

Project context file for **Dynamic IoT Asset Analytics for Giga-Projects**, built by Team FILO for the MENA Open Gateway Hackathon (GSMA MENA Ignite).

---

## 1. Hackathon Info

### About the Hackathon
The MENA Open Gateway Hackathon is an innovation challenge bringing together developers, startups, students, and technology enthusiasts from across the MENA region to build next-generation digital solutions using GSMA Open Gateway CAMARA APIs, the Nokia Network-as-Code platform, and 4G/5G network capabilities.

As the MENA region accelerates digital transformation through smart cities, digital finance, intelligent mobility, connected enterprises, and immersive tourism, the hackathon provides a platform to develop API-powered applications that solve real-world challenges using network intelligence.

Participants build solutions across seven challenge themes, demonstrating how standardized network APIs can power secure, scalable, and intelligent digital services while unlocking new business opportunities across the region.

Prizes: 1st, 2nd, and 3rd place, plus the opportunity for winning teams to showcase their solutions at **MWC Doha (November 2026)**.

### Objectives
- Reward innovation using Open Gateway APIs.
- Support startup development — help early-stage ventures validate and showcase ideas.
- Accelerate adoption of CAMARA APIs, Network-as-Code, and 5G.
- Build developer capabilities in standardized network APIs and next-gen connectivity.
- Foster collaboration between the MENA developer community, regional MNOs, and telecom technology partners.
- Demonstrate the business value of network intelligence through scalable, real-world use cases.

### Eligibility Criteria
Open to individuals and teams from diverse backgrounds: freelancers, working professionals, early-stage startups, students, developers, engineers, designers, entrepreneurs, marketers, innovators — anyone with a great idea and passion for technology.

**Participant requirements:**
- Must be 18+ at time of registration.
- No specific educational qualification or prior experience required.
- Open to all residents of Arab League member countries and Türkiye.

### Seven Challenge Themes
1. **Trusted Digital Identity & Cross-Border Verification** — SIM Swap, Number Verification, Device Status, KYC flows
2. **Smart Cities, Urban Safety & Mega-Project Infrastructure** — Location, QoD, Device Status, Geofencing
3. **Tourism, Pilgrimage & Cultural Experience Innovation** — Location, Device Reachability, QoD
4. **Secure Fintech, Payments & Anti-Fraud Innovation** — SIM Swap, Number Verification, Device Status
5. **Industrial & Enterprise AI Automation** — QoD, Device Status, Network Intelligence
6. **Climate Resilience & Environmental Monitoring** — Location, QoD, Device Status
7. **Open Innovation** — catch-all for ideas spanning multiple themes or beyond current themes

*(Our submission targets Theme 2: Smart Cities, Urban Safety & Mega-Project Infrastructure.)*

### Problem Statement
Build an innovative solution that leverages GSMA Open Gateway CAMARA APIs, the Nokia Network-as-Code platform, and 5G connectivity to solve real-world business and everyday challenges across the MENA region. The solution should demonstrate how network intelligence can create secure, intelligent, and scalable digital services while addressing a meaningful real-world use case.

### Mandatory Requirements
1. **Utilize CAMARA APIs** — at least one CAMARA API available on the Nokia Network-as-Code platform:
   - QoS on Demand
   - Device Status
   - Location Verification
   - Location Retrieval
   - Geofencing
   - Device/Application Attachment
   - Network Slicing
   - Congestion Insights
   - SIM Swap
   - Number Verification
2. **Build an AI Agent Layer** — must intelligently orchestrate one or more CAMARA APIs as trusted, real-time data sources (not simple user-triggered actions). The agent should:
   - Make intelligent decisions using telecom network signals
   - Automate workflows
   - Power AI assistant / copilot experiences
   - Leverage signals such as Number Verification, SIM Swap, Device Status, Location, and Network Quality
   - Be built **only** using tools listed in the AI Resource & Tooling Guide — no external tooling permitted for this component.
3. **Original Solution** — all submitted code must be original; solution must clearly solve or improve a real-world problem.
4. **Theme Alignment** — must align with one of the seven challenge themes.

### Good-to-Have
- Utilize multiple CAMARA APIs on Nokia Network-as-Code.
- Build an application optimized for 5G-capable devices.
- Demonstrate intelligent orchestration across multiple network APIs.
- Design a scalable, secure, production-ready solution.

### Restrictions
- Must utilize 1+ network API available on Nokia Network-as-Code platform.
- Must use original code.
- Must use one of the 7 theme categories.
- Must include an AI agent layer orchestrating one or more CAMARA APIs, built only with tools from the linked Resource and Tooling Guide.

### Evaluation Criteria

The hackathon has two phases. Teams must qualify in Phase 1 to advance to the Live Demo Round (Phase 2).

**Phase 1: Idea Evaluation** (based on Idea Capture Template + Pitch Deck)
- **Relevance:** alignment with one of the seven MENA challenge themes; relevance to regional challenges and local context.
- **Impact:** potential to scale across MENA; clear business model or socio-economic value; thoughtful planning and effort.
- **Innovation:** originality; creative approach to the problem; ability to address meaningful regional pain points.
- **Complexity & Implementation:** technical depth; clear/easy-to-understand solution design; effective use of Open Gateway/CAMARA APIs; feasible, well-defined technical architecture; AI agent design that intelligently orchestrates CAMARA APIs using only the approved Resource & Tooling Guide.

**Phase 2: Live Demo Evaluation** (shortlisted teams present a working prototype)
- **Innovation & Originality:** creativity/uniqueness; innovative application of Open Gateway APIs.
- **Impact:** ability to solve real-world MENA challenges; value delivered to users, businesses, or society.
- **Scalability & Commercial Viability:** potential for large-scale adoption; sustainable business model; commercial readiness beyond the hackathon.
- **Technical Feasibility & Open Gateway API Usage:** quality/depth of CAMARA API integration; functionality and stability of the prototype; smooth end-to-end UX.
- **Agentic AI & Multi-API Orchestration:** intelligent orchestration of one or more CAMARA APIs; effective use of AI agents for automation and decision-making.
- **Presentation & Pitch:** clarity/structure of presentation; ability to communicate problem, solution, technical approach, and business value.

---

## 2. Our Idea — Dynamic IoT Asset Analytics for Giga-Projects

**Team:** FILO (Yazan Zarka, Faris Alshafie, Yazan Abed, Omar Hawasheen)
**Theme:** Smart Cities, Urban Safety & Mega-Project Infrastructure

### Elevator Pitch
An intelligent operations solution for the scale and complexity of MENA mega-developments like NEOM, Red Sea Global, and Qiddiya. Its core problem is deceptively simple: if a piece of heavy machinery stops sending telemetry, site managers have no way of knowing whether it's broken down, the sensor failed, or it just drove into a cellular dead zone. The current default is to send a field engineer — an expensive, time-consuming gamble that often ends with a mechanic standing next to a perfectly functional excavator that simply lost signal. That guesswork compounds at giga-project scale — hundreds of machines spread over thousands of square kilometers.

### How It Works
An AI Agent serves as an autonomous diagnostic layer connecting telemetry data, machine learning, and telecom network APIs:
1. As soon as an asset stops transmitting, the agent queries the **CAMARA Device Status (Reachability) API** to verify network health at that location.
   - If the network is down → flagged as a connectivity issue, no dispatch.
   - If the network checks out → silence is confirmed as an actual hardware/sensor failure.
2. ML models trained on historical asset data predict what has failed or is about to fail.
3. The **CAMARA Location Retrieval API** pulls network-verified coordinates to automatically generate a work order and route the nearest technician with the right parts.

### Key Strategic Pillars (from pitch deck)
- **Core Telecom APIs:** CAMARA Device Reachability Status API (network connectivity truth layer — distinguishes cellular outage from hardware failure in real time) + CAMARA Location Retrieval API (network-verified spatial coordinates for precision dispatch across remote mega-site terrain).
- **Autonomous AI Diagnostics:** self-directed root cause investigation before any field action is triggered; real-time network state verification via CAMARA API layer.
- **Predictive Asset Maintenance:** ML-driven failure forecasting days before catastrophic breakdown.
- Powered by **Nokia Network as Code** — GSMA Open Gateway compliant.

### Regional Context / Problem Framing
MENA mega-developments — NEOM, Red Sea Global, Qiddiya, Masdar City, Msheireb Doha — span thousands of square kilometers of harsh desert terrain, where cellular coverage varies dynamically across active construction zones. When real-time asset visibility breaks down, consequences cascade across schedules, budgets, and safety:
- **Wasted Dispatches** — sending mechanics/trucks into remote desert only to find a machine with lost cell signal, burning fuel, labor hours, and crew safety margins.
- **Catastrophic Failure** — unnoticed mechanical faults left unchecked cause project delays and penalty fees.
- **Operational Friction** — high fuel consumption, safety risks for field crews, degraded asset lifecycle.

### Autonomous AI Agent Orchestration Engine
An AI-powered IoT platform acting as intelligent middleware between field equipment, predictive ML algorithms, field operations, and cellular networks via Nokia Network as Code APIs.
- **Autonomous Incident Triaging:** AI Agent independently investigates root causes before acting — no human intervention needed at the diagnostic stage.
- **Dynamic Network Verification:** queries real-time network states via CAMARA APIs before flagging hardware anomalies — every alert is network-truth-validated before escalation.
- **Closed-Loop Dispatching:** automatically matches diagnostic findings with spatial location data to route engineers with the exact required spare parts.
- Operates as a fully autonomous decision loop: **Anomaly Detect → Network Verify → Closed-Loop Action** — no manual triage at any stage.

### CAMARA API Details
**Device Reachability API — Network Truth Layer**
- Ultimate source of network truth when telemetry streams stop; AI Agent queries device connectivity the moment a heartbeat drops, eliminating ambiguity that drives false dispatches.
- Diagnostic Decision Logic: Status "Connected" → network healthy, hardware failure confirmed, ML model activates for predictive fault classification, dispatch authorized. Status "Disconnected/Roaming Out" → system flags cellular outage, pauses hardware alerts, schedules automated re-check, notifies operator — no mechanic dispatched.

**Location Retrieval API — Precision Spatial Intelligence**
- Fetches real-time, network-verified spatial coordinates directly from mobile network infrastructure, bypassing inaccurate/tampered GPS data on silent devices.
- Dispatch Enablement Logic: enables automated dispatch to locate assets in remote/rapidly changing mega-sites where GPS spoofing or signal loss makes device-reported coordinates unreliable — network-side location is authoritative.

**Combined API Synergy:** together, these APIs eliminate false network-driven alarms while cutting MTTR (mean time to repair) via pinpoint field dispatch.

### Solution Architecture (4 layers)
- **Layer 1: Data Ingestion & Telemetry** — real-time ingestion of CAN-bus, engine temperature, vibration, and GPS sensor data from fleet assets into the IoT gateway; continuous high-frequency streams from every connected heavy asset on site.
- **Layer 2: AI Agent & Logic Orchestration** — AI Agent evaluates incoming telemetry anomaly signals and formulates tool calls to external telecom endpoints and internal ML models; autonomous triage with no human bottleneck.
- **Layer 3: Network as Code API Integration** — secure REST/SDK interface calling Nokia's Network as Code portal; CAMARA Device Status and Location Retrieval endpoints deliver authoritative network state and spatial data.
- **Layer 4: Action & Operational Dashboard** — automated work-order generation, technician routing, and a live executive dashboard updating fleet availability metrics.

### Step-by-Step Incident Resolution Workflow
1. **Stage 1 — Event Trigger:** an excavator on a remote site stops sending diagnostic heartbeats; telemetry stream goes dark.
2. **Stage 2 — Automated Verification:** AI Agent catches the dropped feed and immediately triggers a CAMARA Device Status API check — no human escalation required.
3. **Stage 3A — Network Issue (Scenario A: Cellular Blindspot):** status reveals lost cell connection. Agent logs "Cellular Blindspot," schedules re-check, alerts operator. No dispatch — zero wasted field resources, full operational efficiency maintained.
4. **Stage 3B — Hardware Failure (Scenario B: Confirmed Hardware Fault):** network is active. ML model analyzes past vibration trends, predicting e.g. hydraulic pump failure with high confidence.
5. **Stage 4 — Precision Resolution:** Agent calls CAMARA Location Retrieval API, locks asset coordinates, assigns nearest technician, issues work order with the precise replacement part. Nearest technician routed, work order auto-generated, MTTR minimized, asset back online faster.

### Commercialization, Pricing & Market Expansion
**Target Customers:** main contractors, master developers, heavy equipment rental fleets across the MENA giga-project corridor.
- Saudi Arabia — NEOM & Red Sea Global (unprecedented scale, extreme terrain, maximum efficiency demand); Masdar City — sustainability-driven operations.
- Qatar — Msheireb Doha (dense urban mega-development, complex fleet coordination).

**Revenue Streams:**
1. **Tiered SaaS Subscription** — B2B enterprise licensing charged per connected heavy asset/vehicle per month; scales directly with fleet size and site expansion.
2. **Value-Based API Premium** — tiered pricing based on automated API call volume and AI Agent decision density; customers pay proportionally to intelligence consumed and dispatches avoided.

**Cost Structure Efficiency:** low operational cost via cloud-native serverless functions and pay-per-use telecom API models — infrastructure scales with demand, not ahead of it.

### Measurable Outcomes & Socio-Economic Impact
- **40%** False Dispatch Reduction — verifying device network status before rolling service trucks into the desert.
- **25%** Downtime Reduction — predictive ML analytics identify failure patterns days before catastrophic breakdown, shifting from reactive to proactive maintenance.
- **15%** OpEx Reduction — savings in fuel consumption, mechanic labor hours, and premature part replacements.
- **Field Safety Impact:** fewer false dispatches → fewer crew-hours in high-risk remote/extreme-heat environments.
- **ESG & Carbon Footprint:** eliminating wasted dispatch journeys lowers project carbon footprint; supports sustainability reporting for ESG-committed developers like Masdar City and NEOM.

### Development Roadmap
- **Phase 1 — Concept & Architectural Framing (Current Hackathon Phase):** problem validation, end-to-end user journey mapping, complete API integration logic design — full architectural blueprint established.
- **Phase 2 — Sandbox Prototype & SDK Integration (Next Milestone):** integration with Nokia Network as Code developer portal using synthetic telemetry simulators and Model Context Protocol (MCP) tooling; live API calls validated in sandbox.
- **Phase 3 — Pilot Deployment & Scale (Future Phase):** live field trials with regional telecom partners (STC / Mobily / e&) on active giga-project sites — real fleet data, real network conditions, real operational impact.

### Team FILO
Cross-functional team combining backend engineering, cloud architecture, data science, and AI orchestration expertise — built to deliver end-to-end from API integration to predictive intelligence.
- **Yazan Zarka** — Software Engineer: backend systems, API integration logic, platform workflow execution — connective tissue between CAMARA endpoints and the AI orchestration layer.
- **Faris Alshafie** — Software Engineer: cloud platform architecture, frontend integration, interface usability — ensuring the operational dashboard delivers clarity at executive and field levels.
- **Yazan Abed** — Data Scientist: predictive maintenance modeling, telemetry anomaly detection, ML pipelines — the intelligence engine behind every failure prediction.
- **Omar Hawasheen** — Data Scientist: AI Agent orchestration logic, prompt modeling, data analytics — architecting the autonomous decision loops that power closed-loop dispatching.

*Tagline: FILO @ GSMA MENA Ignite Hackathon — Dynamic IoT Asset Analytics for Giga-Projects | Powered by CAMARA Device Status API & Location Retrieval API via Nokia Network as Code.*

---

## 3. Live Demo Info (Phase 2 Evaluation)

Shortlisted teams present a working prototype during the live demo round. Judged on:

- **Innovation & Originality:** creativity and uniqueness of the solution; innovative application of Open Gateway APIs.
- **Impact:** ability to solve real-world challenges in the MENA region; value delivered to users, businesses, or society.
- **Scalability & Commercial Viability:** potential for large-scale adoption; sustainable business model; commercial readiness beyond the hackathon.
- **Technical Feasibility & Open Gateway API Usage:** quality and depth of CAMARA API integration; functionality and stability of the prototype; smooth end-to-end user experience.
- **Agentic AI & Multi-API Orchestration:** intelligent orchestration of one or more CAMARA APIs; effective use of AI agents for automation and decision-making.
- **Presentation & Pitch:** clarity and structure of the presentation; ability to communicate the problem, solution, technical approach, and business value.

**Demo build target:** live/sandbox demonstration of the closed-loop flow — anomaly detection → CAMARA Device Status check → (network-down: log + notify, no dispatch) or (network-up: ML fault prediction → CAMARA Location Retrieval → auto work order + technician routing) — using synthetic telemetry simulators and Nokia Network as Code sandbox endpoints (per Phase 2 of our roadmap).
