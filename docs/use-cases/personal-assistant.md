# Personal assistant via Telegram

Status: **Reference**
Date: 2026-04-01

## The scenario

Marcus runs several projects simultaneously and keeps a packed calendar. He wants to interact with his own information — schedule, task list, grocery list, personal notes — without opening a laptop. He prefers text over voice, and he wants the assistant to respond only when spoken to, except for genuinely urgent situations where it should reach out first.

Agience powers a Telegram bot that handles conversational requests naturally. Marcus can ask what is on his calendar today, add an item to a list, capture a note, schedule a new event, or ask a question answered from his own knowledge. The assistant tracks short-term conversation context (so "move the 2pm" resolves correctly after asking about tomorrow's schedule) and longer-term preferences (timezone, commute time, preferred store). A parallel scheduled operator monitors for urgent conditions — imminent calendar conflicts, overdue tasks, urgent emails — and initiates a Telegram message proactively when something genuinely needs attention.

---

## What this demonstrates

- Webhook-triggered operators (Telegram message arrives, operator fires)
- Intent classification routing — a single entry point handles many interaction types
- Conversation context management across multiple turns
- Cross-tool coordination (calendar, workspace search, list management)
- Proactive, outbound notifications from a scheduled operator
- User preference persistence across sessions

---

## How it works

1. **Receive** — A Telegram message arrives via webhook and triggers the conversation-handler operator, passing the message text and recent conversation history.

2. **Classify intent** — A language model classifies the message: schedule question, task question, list question, add-to-list command, create-event command, general knowledge question, or note capture. Each intent also carries extracted entities (time references, item names, list type) and a flag indicating whether a reply is expected.

3. **Route** — A conditional branch acts on the intent:
   - Schedule questions query the connected calendar, then format a conversational response with travel time and conflict notes.
   - Task questions search the inbox workspace for open action-item artifacts.
   - List commands append to or return the relevant list artifact (grocery, to-do, or a named list).
   - Event commands extract structured date and time from natural language and create a calendar event.
   - General questions run a workspace search and synthesize a short answer from matching artifacts.
   - Notes are stored as artifacts with minimal acknowledgment.

4. **Reply** — The formatted response is sent back to the user's Telegram chat.

5. **Update history** — The conversation history artifact is appended with the latest exchange, trimmed to the most recent ten turns.

6. **Proactive check** — A separate operator runs every five minutes. It checks for urgent unread emails, imminent calendar conflicts, and overdue tasks. If any threshold is crossed, it formats a concise notification and sends it unsolicited to the user's Telegram.

---

## Agience primitives used

| Primitive | Role |
|-----------|------|
| Workspace | Stores task artifacts, list artifacts, notes, and conversation history |
| Artifact | Each list, note, conversation history, and task is a persisted artifact |
| Operator (webhook) | Fires on every inbound Telegram message |
| Operator (scheduled) | Runs every five minutes to check for urgent conditions and notify proactively |
| MCP server (Telegram) | Provides `send_message` and webhook delivery for the bot |
| MCP server (calendar) | Provides event queries, event creation, and conflict detection |
| Context (user preferences) | Persisted preferences (timezone, commute time, notification threshold) shape every response |

---

## Getting started

Create a Telegram bot via BotFather, configure the webhook to point at your Agience instance, and link a calendar account. Start with [quickstart.md](../getting-started/quickstart.md) and [agent execution](../features/agent-execution.md).
