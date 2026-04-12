# Intelligent email management

Status: **Reference**
Date: 2026-04-01

## The scenario

Sarah is a product manager who receives more than a hundred emails every day. Customer feedback, bug reports, meeting invites, newsletters, sales inquiries, and team updates all land in the same inbox. She spends the first hour of every morning triaging, and important messages still get buried. Newsletters pile up unread. She types variations of the same reply dozens of times a week.

Agience monitors her inbox on a schedule, classifies each message as it arrives, and routes it to the right outcome: urgent items get surfaced immediately with a notification, action-required messages produce ready-to-send draft replies, newsletters get queued for a weekly digest, and action items land in her workspace as artifacts. Nothing sends automatically — Sarah reviews and approves every outbound message — but the cognitive work of sorting and drafting is already done.

---

## What this demonstrates

- Scheduled, recurring operator execution (poll email every five minutes)
- Conditional branching — different outcomes for different classifications
- Parallel processing of multiple items in the same run
- Human-in-the-loop (HITL) gates before sending drafted responses
- Multi-step chained workflows across multiple MCP servers
- Newsletter consolidation via a second scheduled operator

---

## How it works

1. **Fetch** — An operator runs on a schedule and retrieves all unread messages since the last check from the connected email account.

2. **Classify** — Each email is processed in parallel. A language model assigns category (work, personal, newsletter, notification), urgency (urgent, important, normal, low), and flags whether the message requires action or a reply.

3. **Route** — A conditional branch acts on the classification result:
   - Urgent emails create workspace artifacts tagged `urgent` and trigger a push notification.
   - Action-required emails have their action items extracted into individual workspace artifacts.
   - Messages that need a reply get a draft response generated and saved as a workspace artifact for review.
   - Newsletters are queued in a collection for weekly consolidation.
   - Everything else creates a lightweight informational artifact.

4. **Mark processed** — Emails are marked as read in the source account after all branches complete.

5. **Update state** — A timestamp artifact is updated so the next run knows where to resume.

6. **Newsletter digest** — A second operator runs weekly. It retrieves the queued newsletter collection, groups by sender, summarizes each publication's week, and produces a single digest artifact. The queue is cleared.

7. **Review and act** — Sarah opens her workspace, sees prioritized artifacts, reviews any draft replies, edits as needed, and sends. Nothing leaves her account without her approval.

---

## Agience primitives used

| Primitive | Role |
|-----------|------|
| Workspace | Staging area where extracted emails, action items, and draft replies appear as artifacts |
| Artifact | Each email outcome (urgent alert, action item, draft reply, digest) stored as a typed, taggable artifact |
| Collection | Newsletter queue — persisted across runs, cleared after each digest is produced |
| Operator (scheduled) | Runs the email-monitoring workflow every five minutes |
| Operator (scheduled) | Runs the newsletter consolidation workflow weekly |
| MCP server (email) | Provides `fetch_unread`, `mark_as_read`, and `send_email` tools |
| MCP server (notification) | Delivers push notifications for urgent classifications |
| HITL gate | Draft artifacts require human review and explicit approval before being sent |

---

## Getting started

Connect an email account via the MCP email server, configure the operator schedule and urgency threshold, and point it at a workspace to receive artifacts. Start with [quickstart.md](../getting-started/quickstart.md) and [agent execution](../features/agent-execution.md).
