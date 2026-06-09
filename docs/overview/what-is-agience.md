# What Is Agience

Status: **Reference**
Date: 2026-05-09

---

## What It Is

**Agience is the AI knowledge platform with provenance built in.**
Encrypted by default. MCP-native. Self-hostable. Open source.

Every artifact in Agience carries its own provenance — sources, evidence,
transform, actor, version lineage — in its context. Storage gets ciphertext;
hybrid search runs on encrypted indexes; the storage layer never reads
plaintext content or queries. Curation flows through an explicit commit
boundary so AI can assist broadly without silently becoming the system of
record.

Agience gives teams a structured place to capture, curate, and commit
information — and lets AI agents operate on that same information through
the Model Context Protocol. The platform is built around two surfaces:
**Workspaces**, where work happens in a fast, editable, high-churn
environment, and **Collections**, where reviewed knowledge is committed as
durable, versioned artifacts. Humans see cards in the UI; agents see
artifacts through the API or MCP tools — same data, two surfaces.

Agience is MCP-native. Agents (Claude, VS Code, Cursor, custom) connect
to a single MCP endpoint and reach everything they need: first-party
tools, persona handlers for domain capabilities, and any registered
vendor's official MCP server (GitHub, Drive, Slack, Notion, Linear,
more) — Agience proxies through to them rather than re-implementing
them. Identity and provenance travel with every call. Hybrid search
(keyword + semantic) runs on encrypted indexes — the storage layer
never reads plaintext content or queries. Artifacts are stored in
ArangoDB; large content lives in S3-compatible storage; identity lives
in Postgres.

A premium tier — **Anchored reasoning** — adds a patent-pending mechanism
that goes further: it anchors *every AI answer* to verified evidence in
your encrypted memory and signals explicit gaps when the evidence doesn't
warrant a conclusion. That's how you stop AI from making things up.
Anchored reasoning is the layer that does the stopping; Agience-the-platform
is the encrypted, provenance-rich substrate that makes it possible.

---

## The Problem It Solves

AI is generating more outputs than ever, and fewer of them are reliable.
Meetings produce partial notes; decisions lose their supporting reasoning;
AI-generated summaries accelerate output while weakening traceability; teams
end up operating on degraded copies of their own thinking. When AI invents what
it can't verify, nobody can audit the difference.

Agience solves this by giving knowledge a home with structure. Humans and AI
agents work on the same artifacts. A commit boundary separates working draft
from published truth, so AI can assist broadly without silently becoming the
system of record. Every artifact carries its own provenance, so the path from
raw input back to source material is always inspectable. Add the Anchored
reasoning tier when you need AI answers themselves to be anchored to
verified evidence — that's the layer that prevents hallucinations.

The result is an inspectable, encrypted, versioned knowledge base where the
path from raw input to reviewed knowledge is preserved — not flattened. The
trustworthy AI sits on top of it.

---

## How It Works

- **Capture**: Ingest files, transcripts, media, webhooks, and external events into a Workspace. Workspace content is fast, editable, and ephemeral — nothing is canonical until it is committed.
- **Curate**: Run AI-assisted extraction, synthesis, and analysis over workspace artifacts. Agents can propose structure and surface candidates; humans review the results in the workspace UI.
- **Commit**: Explicitly promote selected artifacts from a Workspace into a Collection. The commit step is intentional friction — it keeps draft output from silently becoming doctrine.
- **Search and query**: Committed artifacts are indexed in encrypted MANTLE+SSE blobs (lexical BM25 over blind tokens + encrypted IVF vector), fused via RRF. The storage layer never sees plaintext. Collections are the authoritative source; workspaces provide supplementary draft context.
- **Extend via MCP**: Connect external MCP servers (vendor tools, first-party persona servers) to add capabilities without rebuilding integrations inside the platform.

---

## Key Concepts

**Artifact** — The core unit of stored knowledge. An artifact has a unique ID, a content payload (text or binary), a content type (MIME), and a `context` object carrying metadata (title, tags, provenance, semantic kind). Workspace artifacts are mutable drafts; collection artifacts are immutable once committed.

**Workspace** — A draft staging area backed by ArangoDB. Artifacts can be freely created, edited, reorganized, and deleted here. Agents write to workspaces; humans curate here before committing.

**Collection** — A named, versioned set of committed artifacts backed by ArangoDB. Collections are the source of truth. Every commit creates a new version. History and provenance are preserved.

**Commit** — The explicit act of promoting one or more workspace artifacts into a collection. Commits are gated: `commit_preview` returns a token, which must be passed to `commit_workspace` after human review. The server rejects commits without a valid token.

**Agent** — Any process that reads from collections or writes to workspaces via the API or MCP tool surface. Agents can propose artifacts but cannot silently rewrite committed truth.

**MCP (Model Context Protocol)** — The protocol Agience uses for tool and resource access. Agents see a single MCP endpoint; Agience handles internal calls on the encrypted substrate, dispatches to first-party persona MCP servers, and proxies calls to registered vendor MCP servers (GitHub, Drive, Slack, Notion, Linear, more) — official-first, never re-implementing the vendor API. Any MCP-capable client — VS Code Copilot, Claude Desktop, Cursor, or a custom agent — can connect.

---

## What You Can Build

- **AI-assisted research pipelines**: Ingest documents or transcripts, run extraction with `extract_information`, review candidate artifacts in the workspace, and commit reviewed findings to a durable collection.
- **Team knowledge bases**: Accumulate decisions, meeting notes, and reference material across a team. Commit-gated curation keeps the collection clean; hybrid search makes it retrievable.
- **Event-driven workflows**: Use workspace automation to process incoming artifacts with operator-based event handlers, extraction, and routing.
- **Agent memory layers**: Give any MCP-capable agent persistent, searchable memory backed by versioned collections rather than local text files that grow unbounded.

See [Use Cases](../use-cases/README.md) for detailed examples.

---

## How to Get Started

**Hosted trial** — The fastest path. Log in, get a workspace provisioned automatically, and connect an MCP client in minutes. See [quickstart.md](../getting-started/quickstart.md).

**Self-hosted** — Run Agience on your own infrastructure with full control over your data. Requires Docker Compose, Google OAuth credentials, and an OpenAI API key for embeddings. See [getting-started/self-hosting.md](../getting-started/self-hosting.md).
