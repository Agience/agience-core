# Meeting intelligence

Status: **Reference**
Date: 2026-04-01

## The scenario

Lisa is a senior product manager who runs planning sessions, architecture discussions, customer calls, and retrospectives throughout the week. After every meeting she faces the same problem: she needs to write up notes, extract action items, email a summary to participants, and — when the conversation was technical — start on a proof-of-concept before the ideas cool down. This work routinely takes two to four hours per meeting and frequently falls behind.

Agience processes a meeting recording automatically when the meeting ends. It transcribes the audio with speaker identification, segments the conversation by topic, and runs several parallel analyses to extract action items, decisions, technical content, and open questions. It then synthesizes comprehensive notes in Markdown, generates proof-of-concept code when a technical discussion was detected, drafts a follow-up email for participants, and places all of these artifacts in the workspace ready for review. The whole process takes a few minutes. Lisa opens her workspace, scans the notes, checks the draft code, tweaks the email, and sends. Manual note-taking after a meeting is no longer part of her workflow.

---

## What this demonstrates

- Long-running, multi-step orchestration triggered by a webhook when a meeting ends
- Parallel analysis passes running against a single transcript simultaneously
- Conditional code generation — only triggered when technical content was detected
- Multi-artifact output — notes, action items, decision records, code, and email draft all created in a single run
- Integration with transcription, calendar, and email MCP servers
- HITL gate before the follow-up email is sent

---

## How it works

1. **Transcribe** — When the meeting ends, a webhook triggers the operator. If a transcript is not already available, the transcription MCP server processes the recording audio with speaker diarization enabled.

2. **Segment** — The full transcript is analyzed to identify logical topic sections, each with a time range, summary, and key participants.

3. **Parallel analysis** — Four analyses run in parallel against the same transcript:
   - Action item extraction (what, who, when, priority, context)
   - Decision extraction (what was decided, by whom, rationale, alternatives considered)
   - Technical content extraction (code snippets, schemas, architecture choices, technologies mentioned)
   - Questions and concerns extraction (raised by whom, resolved or still open)

4. **Synthesize notes** — A language model combines all four analysis outputs into a structured Markdown document: summary, discussion topics by segment, decisions, action items, technical details, open questions, and next steps.

5. **Generate proof-of-concept** — If technical content was detected and the `generate_poc` flag is set, a code-generation MCP server produces a working implementation based on the discussion, including data models, core logic, basic tests, and setup instructions.

6. **Create artifacts** — In parallel:
   - A meeting notes artifact is created in the `meetings` workspace.
   - One action-item artifact is created per extracted action, placed in the `inbox` workspace.
   - Decision artifacts are created in the `decisions` workspace.
   - If code was generated, a proof-of-concept artifact is created in the `code` workspace.

7. **Draft follow-up email** — A follow-up email is drafted for all participants, summarizing the meeting, listing decisions and action items with owners, and linking to the full notes artifact.

8. **Notify** — A Telegram message confirms the workspace was populated and provides a link to the notes artifact.

---

## Agience primitives used

| Primitive | Role |
|-----------|------|
| Workspace | Receives all output artifacts (notes, actions, decisions, code) |
| Artifact | Each output — meeting notes, individual action items, decision records, POC code, email draft — is a separate artifact |
| Operator (webhook) | Triggered when the meeting recording is ready |
| MCP server (transcription) | Provides audio-to-text with speaker diarization |
| MCP server (code generation) | External code-generation server (not built-in — requires connecting a third-party or custom MCP server) |
| MCP server (calendar) | Provides meeting metadata and participant list |
| MCP server (email) | Delivers the follow-up email after human review |
| HITL gate | Follow-up email artifact requires review and explicit send action |

---

## Getting started

Configure a meeting recording source (Zoom, Google Meet, or a local recording), connect a transcription provider, and point the operator webhook at your Agience instance. Start with [quickstart.md](../getting-started/quickstart.md) and [agent execution](../features/agent-execution.md).
