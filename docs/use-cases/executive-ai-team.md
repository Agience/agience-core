# Executive AI team

Status: **Reference**
Date: 2026-04-01

## The scenario

Marcus is the CEO of a fifty-person startup. Every week he needs to know his cash position and runway, understand where the sales pipeline stands and what the quarter will close at, and figure out which marketing investments are actually driving revenue. In practice this means chasing his finance team, waiting for Excel exports, and spending the last night before every board meeting assembling a deck from scattered sources. By the time the numbers are in front of him they are already a week old.

Agience runs three specialized agents — an AI CFO, an AI CRO, and an AI CMO — each pulling from the authoritative source systems and delivering a focused report on a regular schedule. The CFO agent monitors bank balances, burn rate, and runway daily and fires a critical alert via Telegram if an anomaly crosses a configured threshold. The CRO agent analyzes the sales pipeline weekly, applies probability weighting by stage and deal velocity, and produces a revenue forecast with confidence intervals. The CMO agent evaluates campaign attribution and ROI across channels. When a board meeting approaches, a fourth operator — the board deck generator — synthesizes all three streams of accumulated reports into a presentation draft, ready for Marcus to review and approve. What previously took ten hours of manual work now takes forty-five minutes of review.

---

## What this demonstrates

- Multiple independently scheduled operators, each scoped to a single executive domain
- Multi-source data integration (accounting, CRM, ad platforms, banking) in a single run
- Anomaly detection with configurable thresholds and conditional alerting
- Time-series artifacts — daily snapshots committed to collections form the historical record
- On-demand document generation synthesizing weeks of accumulated artifacts
- Human-in-the-loop review gate before board materials are distributed

---

## How it works

1. **Daily financial snapshot (AI CFO)** — Runs at 7am. Fetches current bank balances and Stripe revenue in parallel, pulls month-to-date and quarter-to-date figures from the accounting system, calculates burn rate and runway, and runs anomaly detection against the last six months of daily snapshots. If burn increased more than 15% or runway dropped below 12 months, a critical alert fires via Telegram. A CFO report artifact is created in the `executive-reports` workspace and committed to the daily snapshots collection.

2. **Weekly pipeline forecast (AI CRO)** — Runs Monday morning. Fetches all open opportunities from the CRM with stage history, calculates median days per stage as a velocity indicator, and asks a language model to produce a probability-weighted revenue forecast for the current and next quarter. A strategic analysis pass identifies at-risk deals, concentration risk, and rep performance outliers. The CRO report artifact is placed in the `executive-reports` workspace.

3. **Campaign analysis (AI CMO)** — Runs on a configurable schedule. Pulls spend and performance data from each ad platform, calculates multi-touch attribution and ROI by channel and campaign, and identifies top performers and underperformers. Recommendations for budget reallocation are generated based on historical conversion data. The CMO report artifact is placed in the `executive-reports` workspace.

4. **Board deck generation (on demand)** — Marcus triggers this operator before a board meeting. It searches the `executive-reports` workspace for all CFO, CRO, and CMO artifacts from the target period, extracts the key metrics from each, asks a language model to craft a coherent narrative, and passes the narrative and data to a presentation-generation MCP server that produces a slide deck.

5. **Review gate** — The generated deck is not sent automatically. A gate artifact is created with options to approve and send, or request changes. Marcus reviews, makes minor edits if needed, and approves. The deck link goes to board members only after that confirmation.

---

## Agience primitives used

| Primitive | Role |
|-----------|------|
| Workspace | Staging area for daily, weekly, and on-demand report artifacts |
| Collection | Committed daily snapshots form the immutable historical record used for trend analysis |
| Artifact | Each CFO, CRO, CMO, and board deck report is a typed artifact with structured context |
| Operator (scheduled) | Three independently scheduled agents, each producing domain-specific artifacts |
| Operator (manual) | Board deck generator triggered on demand |
| MCP servers (accounting, CRM, banking, ad platforms) | Authoritative data sources for each executive domain |
| MCP server (presentation) | Generates the slide deck from structured narrative and metrics |
| HITL gate | Board deck review step before any material is distributed |
| Anomaly detection | Configurable thresholds trigger conditional Telegram alerts |

---

## Getting started

Connect your accounting system, CRM, and banking provider via the relevant MCP servers and configure the schedule and alert thresholds for each agent. Start with [quickstart.md](../getting-started/quickstart.md) and [agent execution](../features/agent-execution.md).
