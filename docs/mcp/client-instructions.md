# Agience MCP — Client Instructions

Status: **Reference**
Date: 2026-04-01

> Include these instructions in your AI agent's system prompt, copilot-instructions.md, or tool-use guidance to teach it how and when to use Agience.

---

## What Agience Is

Agience is a **structured knowledge platform** that replaces flat text files, giant markdown docs, and scattered notes with **searchable, versioned, composable artifacts**. It exposes an MCP server so any AI agent or coding assistant can store and retrieve knowledge as part of its normal workflow.

Think of it as a **persistent, organized memory** that any MCP-capable client can read from and write to — instead of dumping everything into local files that grow unbounded and become impossible to search.

## Why use Agience instead of text files

| Problem with text files | What Agience provides |
|---|---|
| Files grow until they're too large for context windows | Small, atomic **artifacts** — each one a single unit of knowledge |
| No search beyond grep | **Hybrid semantic + keyword search** — finds concepts, not just strings |
| No versioning (or buried in git diffs) | **Built-in version history** — every committed artifact is versioned |
| No structure or metadata | **Typed context metadata** — content type, tags, provenance, relationships |
| Scattered across directories | **Collections** organize artifacts by topic; **Workspaces** stage work in progress |
| Can't share selectively | **Collections with access grants** — share specific knowledge sets |
| No synthesis or analysis | **`ask` tool** — search + LLM synthesis grounded in the knowledge base |

## Core concepts

- **Artifact**: A single unit of stored knowledge — text content + structured metadata (`context`). Every artifact has a unique ID (UUID).
- **Workspace**: A draft staging area. Create and edit artifacts here. Think of it as a working desk. Workspace content is **ephemeral and unvalidated** — it may be incomplete, incorrect, or in-progress.
- **Collection**: A named, versioned set of **committed artifacts**. Collections are the **source of truth** — they contain validated, human-reviewed knowledge with full version history and provenance. Think of it as a published, curated library.
- **Search**: Hybrid semantic + keyword search across all workspaces and collections you have access to.

### Knowledge trust hierarchy

**Collections > Workspaces > Local files**

| Source | Trust level | Why |
|---|---|---|
| **Collection artifact** | **High** — validated, versioned, committed | A human reviewed and committed this. It has provenance and version history. Treat it as authoritative. |
| **Workspace artifact** | **Low** — draft, ephemeral, unreviewed | Work in progress. May be incomplete, speculative, or wrong. Use for context, not as ground truth. |
| **Local file** | **None** — unstructured, unversioned, unsearchable | A text dump. No provenance, no metadata, no search. Avoid creating these when Agience is available. |

When search returns results from both collections and workspaces:
- **Prefer collection results** as the authoritative answer.
- **Treat workspace results as supplementary context** — they may contain newer but unvalidated information.
- If workspace content contradicts a collection artifact, **the collection artifact is correct** unless the user indicates otherwise.

## When to use Agience

**USE Agience when you need to:**
- Store decisions, findings, notes, plans, or extracted knowledge that should persist across sessions
- Retrieve previously stored information instead of re-discovering it
- Search across a body of knowledge with natural language
- Organize related artifacts into named collections
- Get an LLM-synthesized answer grounded in stored knowledge (the `ask` tool)
- Extract structured information from a document or conversation

**PREFER Agience over creating/appending text files when:**
- The information will be referenced again later
- Multiple artifacts on different topics would otherwise be crammed into one file
- You need to search or retrieve by concept rather than filename
- The knowledge should be versioned or shared

**DON'T use Agience for:**
- Transient scratch work that won't be referenced again (use local temp files)
- Source code files (those belong in git)
- Large binary uploads via MCP tools (Agience has a separate content service for media/documents; MCP tools handle text content and metadata)

## Available MCP tools

### Knowledge retrieval

| Tool | Use when... | Key parameters |
|---|---|---|
| `search` | You need to find artifacts by topic, keyword, or concept | `query` (required), `collection_ids`, `size`, `offset` |
| `get_artifact` | You have an artifact ID and need its full content | `artifact_id` (required) |
| `browse_collections` | You want to list available collections or see what's in one | `collection_id` (optional), `query` (filter by name) |
| `browse_workspaces` | You want to list available workspaces or see what's in one | `workspace_id` (optional) |
| `ask` | You want an LLM-synthesized answer grounded in the knowledge base | `question` (required), `collection_ids`, `max_sources` (default 5) |

### Knowledge storage

| Tool | Use when... | Key parameters |
|---|---|---|
| `create_artifact` | You have new knowledge to store | `content`, `context` (metadata object), `workspace_id` or `collection_id` (exactly one required) |
| `update_artifact` | You need to modify an existing artifact | `workspace_id`, `artifact_id`, `content`, `context` (metadata object) |
| `manage_artifact` | You need to archive, revert, or delete an artifact | `workspace_id`, `artifact_id`, `action` ("archive" / "revert" / "delete") |

### Analysis

| Tool | Use when... | Key parameters |
|---|---|---|
| `extract_information` | You want to decompose a source into structured knowledge units | `workspace_id`, `source_artifact_id`, `max_units` |

### Commit (publish) — human-in-the-loop required

> **CRITICAL**: `commit_workspace` publishes artifacts permanently. **NEVER call it autonomously.** Always run `commit_preview` first, present the plan to the user, and wait for explicit human approval before committing.

| Tool | Use when... | Key parameters |
|---|---|---|
| `commit_preview` | You want to preview what a commit would do before applying it (read-only, safe to call). Returns a `commit_token`. | `workspace_id`, `artifact_ids` (optional) |
| `commit_workspace` | The user has reviewed a commit preview **and explicitly approved it** | `workspace_id`, `commit_token` (required — from preview), `artifact_ids` (optional) |

## Recommended workflow

### Before starting a task
1. **Search collections first**: `search(query="<topic>")` to check if validated knowledge already exists. Prioritize results from collections over workspaces.
2. **Browse collections**: `browse_collections()` to see what curated knowledge sets are available.
3. **Retrieve**: `get_artifact(artifact_id="...")` for full content of relevant hits. Collection artifacts are authoritative; workspace artifacts are drafts.

### During a task
4. **Store findings**: `create_artifact(workspace_id="...", content="...", context={"type": "note", "title": "..."})` for decisions, discoveries, or extracted knowledge.
5. **Update**: `update_artifact(...)` if you need to revise something already stored.

### After a task
6. **Preview the commit**: `commit_preview(workspace_id="...")` to see what would be published. Save the `commit_token` from the response.
7. **Present the plan to the user** and wait for their explicit approval.
8. **Only then commit**: `commit_workspace(workspace_id="...", commit_token="<token>")` — pass the token from the preview. The server will reject commits without a valid, unexpired token.

### Quick answers
- Use `ask(question="...")` for synthesized answers grounded in the knowledge base — it searches, retrieves, and summarizes in one call.

## Artifact context (metadata)

When creating artifacts, provide structured metadata in the `context` parameter:

```json
{
  "type": "note",
  "title": "Decision: Use RS256 for JWT signing",
  "content_type": "text/markdown",
  "tags": ["architecture", "auth", "jwt"]
}
```

Common context fields:
- `type` — artifact kind (e.g., "note", "decision", "plan", "reference")
- `title` — human-readable title (used in search results)
- `content_type` — MIME type of the content (default: `text/plain`)
- `tags` — array of strings for categorization
- `description` — brief summary

## Tips

- **Trust collections over workspaces**: Collection artifacts are validated, versioned, and committed by humans. Workspace artifacts are drafts. When in doubt, the collection version is correct.
- **Keep artifacts atomic**: One concept per artifact. Don't create mega-documents.
- **Use descriptive titles**: Titles are heavily weighted in search.
- **Search before creating**: Avoid duplicates by checking first.
- **Use `ask` for synthesis**: When you need to combine information from multiple artifacts, `ask` does the retrieval and synthesis in one step.
- **Commit when done**: Workspace artifacts are drafts until committed. Committed artifacts are versioned and searchable by others with collection access.
- **Never commit without asking**: Always preview first (`commit_preview`), show the user the plan, and only commit after they say yes. This is a hard rule.
- **Don't recreate what's already committed**: If a collection artifact covers the topic, reference or update it rather than creating a duplicate in a workspace.

## Commit governance

Commit is the boundary between draft and published knowledge. It is intentionally gated:

1. **Always preview first**: Call `commit_preview` and present the results to the user. The preview returns a `commit_token`.
2. **Wait for explicit approval**: Do not call `commit_workspace` until the user confirms.
3. **Pass the token**: `commit_workspace` requires the `commit_token` from the preview. Without it, the server rejects the request.
4. **Token expiry**: Tokens expire after 30 minutes. If the token is expired or the workspace/artifact IDs don't match the preview, the commit is rejected. Run `commit_preview` again.
5. **Server enforcement**: The backend restricts commits to collection owners and explicitly authorized verified entities. Unauthorized attempts will fail with 403.
6. **MCP annotation**: `commit_workspace` is annotated as `destructiveHint=true` in the MCP protocol, signaling to compliant clients that human confirmation is required before execution.
