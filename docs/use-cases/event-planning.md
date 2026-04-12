# AI-powered event planning

Status: **Reference**
Date: 2026-04-01

## The scenario

Sarah is planning her daughter's wedding — 150 guests, eight months out, a $45,000 budget, and twelve vendors to coordinate. The information lives everywhere at once: vendor emails scattered across her inbox, RSVPs arriving by text and phone, budget figures in a spreadsheet, inspiration images on Pinterest. Staying on top of deadlines while managing all these threads is a full-time job layered on top of her actual life.

Agience initializes a dedicated event workspace with a master timeline, a phased budget allocation, a guest list tracker, vendor artifacts for each category, and a day-of logistics artifact. From that point it monitors her email and text channels in the background. When a vendor email arrives, relevant action items are extracted and the vendor's artifact is updated. When an RSVP comes in — by email, SMS, or any other channel — it is parsed, classified, and the guest list counts and dietary restrictions update automatically. When a new expense pushes a budget category over its allocation, Sarah receives an alert with specific suggestions for getting back on track. A week before the wedding, a detailed minute-by-minute day-of timeline is generated from all booked vendors, ceremony timing, and setup schedules. Sarah keeps full control — she reviews and approves vendor communications before they go out and makes the final calls on budget decisions — but the organizational burden is handled.

---

## What this demonstrates

- Workspace initialization — a structured set of artifacts created in a single on-demand operator run
- Multi-channel input — email and other message sources feeding the same workflow via webhooks
- Natural language parsing for RSVP extraction with confidence thresholds
- Budget tracking with real-time anomaly alerts and AI-generated recommendations
- Cross-artifact state updates — guest list counts and vendor artifacts updated as events flow in
- Scheduled reminders tied to generated milestone deadlines

---

## How it works

1. **Initialize** — Sarah runs the setup operator with her event details (name, date, type, guest count, budget, venue if known). A language model generates a phased planning timeline with vendor deadlines and critical-path ordering, plus a percentage-based budget allocation by category. The operator creates the workspace and populates it with timeline-phase artifacts, one vendor artifact per category, a budget-tracker artifact, a guest-list artifact, and a day-of logistics artifact.

2. **Vendor management** — The email-monitoring integration is configured to flag vendor-domain emails. When a vendor email arrives, action items are extracted (schedule a session, provide a shot list, confirm headcount) and appended to the relevant vendor artifact. Draft responses are generated for Sarah's review.

3. **RSVP tracking** — An RSVP-tracker operator fires via webhook whenever an email or SMS arrives on the monitored channels. A language model parses the message to determine the response (attending, declined, maybe), guest count, plus-one name, and dietary restrictions. If confidence exceeds 0.8, the guest-list artifact context is updated immediately: confirmed and declined counts increment, dietary restriction tallies update, and a caterer-notification artifact is created if new restrictions were reported.

4. **Budget alerts** — A budget-alert operator fires whenever a new expense is logged. It retrieves the current budget-tracker artifact, calculates new totals and any overage, and updates the artifact. If the new total exceeds the budget, a language model generates specific cost-reduction recommendations (reduce centerpiece complexity, use seasonal flowers, eliminate a low-impact line item). An alert artifact is created and a Telegram notification is sent with the recommendations.

5. **Confirmation replies** — After an RSVP is recorded, a confirmation is automatically sent back to the guest via the same channel they used (email or SMS), acknowledging their response and any dietary notes.

6. **Day-of timeline** — In the week before the event, Sarah triggers the day-of operator. It assembles all booked vendor artifacts, ceremony timing, and setup windows into a minute-by-minute timeline artifact with vendor contacts and check-in notes. On the day itself, milestone reminders fire automatically at configured intervals.

---

## Agience primitives used

| Primitive | Role |
|-----------|------|
| Workspace | Dedicated event workspace containing all planning artifacts |
| Artifact | Timeline phases, vendor profiles, budget tracker, guest list, and day-of schedule each stored as artifacts |
| Operator (manual) | Workspace initialization and day-of timeline generation |
| Operator (webhook) | RSVP tracker fires on inbound email or SMS |
| Operator (event-driven) | Budget alert fires when a new expense is logged |
| MCP server (email) | Monitors vendor communications and sends confirmation replies |
| MCP server (messaging) | Receives RSVPs via connected messaging channels and sends confirmations (requires external MCP server, e.g. Twilio) |
| MCP server (calendar) | Provides scheduling context and milestone reminder delivery |
| HITL gate | Vendor reply drafts require review before being sent |

---

## Getting started

Connect an email account (and optionally an SMS provider such as Twilio via its MCP server), run the workspace-initialization operator with your event details, and configure the RSVP webhook. Start with [quickstart.md](../getting-started/quickstart.md) and [agent execution](../features/agent-execution.md).
