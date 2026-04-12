# What Is Agience

Status: **Reference**
Date: 2026-04-01

---

## What It Is

Agience is a knowledge curation platform. It gives teams a structured place to capture, organize, and commit information — and lets AI agents operate on that same information through a standard protocol (MCP). The platform is built around two surfaces: **Workspaces**, where work happens in a fast, editable, high-churn environment, and **Collections**, where reviewed knowledge is committed as durable, versioned artifacts. Both surfaces expose the same underlying data — humans see cards in the UI, agents see artifacts through the API or MCP tools.

Agience is open source and MCP-native. It runs as both an MCP server (exposing its tools and resources to AI clients) and an MCP client (connecting to external MCP servers and vendor tools). The platform stores all artifact data in ArangoDB (workspaces and collections), with large content in S3-compatible object storage and hybrid search powered by OpenSearch.

---

## The Problem It Solves

Organizations accumulate knowledge in fragmented, disconnected tools — meetings produce partial notes, decisions lose their supporting reasoning, AI-generated summaries accelerate output while weakening traceability, and teams end up operating on degraded copies of their own thinking. The harder problem is not producing more output; it is preserving the reasoning, evidence, and accountability behind it.

Agience solves this by giving knowledge a home with structure. Humans and AI agents work on the same artifacts. A commit model separates working draft from published truth, so AI can assist broadly without silently becoming the system of record. The result is an inspectable, versioned knowledge base where the path from raw input to reviewed knowledge is preserved rather than flattened.

---

## How It Works

- **Capture**: Ingest files, transcripts, media, webhooks, and external events into a Workspace. Workspace content is fast, editable, and ephemeral — nothing is canonical until it is committed.
- **Curate**: Run AI-assisted extraction, synthesis, and analysis over workspace artifacts. Agents can propose structure and surface candidates; humans review the results in the workspace UI.
- **Commit**: Explicitly promote selected artifacts from a Workspace into a Collection. The commit step is intentional friction — it keeps draft output from silently becoming doctrine.
- **Search and query**: Committed artifacts are indexed in OpenSearch with hybrid BM25 + semantic (kNN) retrieval. Collections are the authoritative source; workspaces provide supplementary draft context.
- **Extend via MCP**: Connect external MCP servers (vendor tools, first-party persona servers) to add capabilities without rebuilding integrations inside the platform.

---

## Key Concepts

**Artifact** — The core unit of stored knowledge. An artifact has a unique ID, a content payload (text or binary), a content type (MIME), and a `context` object carrying metadata (title, tags, provenance, semantic kind). Workspace artifacts are mutable drafts; collection artifacts are immutable once committed.

**Workspace** — A draft staging area backed by ArangoDB. Artifacts can be freely created, edited, reorganized, and deleted here. Agents write to workspaces; humans curate here before committing.

**Collection** — A named, versioned set of committed artifacts backed by ArangoDB. Collections are the source of truth. Every commit creates a new version. History and provenance are preserved.

**Commit** — The explicit act of promoting one or more workspace artifacts into a collection. Commits are gated: `commit_preview` returns a token, which must be passed to `commit_workspace` after human review. The server rejects commits without a valid token.

**Agent** — Any process that reads from collections or writes to workspaces via the API or MCP tool surface. Agents can propose artifacts but cannot silently rewrite committed truth.

**MCP (Model Context Protocol)** — The protocol Agience uses for tool and resource access. Agience acts as an MCP server (exposing search, create, commit, and other tools) and as an MCP client (calling external MCP servers). Any MCP-capable client — VS Code Copilot, Claude Desktop, Cursor, or a custom agent — can connect to Agience.

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
