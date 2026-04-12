# Architecture Overview

Status: **Reference**
Date: 2026-04-01

This document introduces the Agience architecture for developers evaluating the platform and operators wanting to understand what they are running. It is not an implementation spec. For deep implementation detail, follow the links at the end of each section.

---

## The OS Analogy

Agience is an **information operating system**. The analogy is not decorative — it describes the actual design choices. An OS separates storage (the filesystem and inode table), execution (processes), device access (drivers), and user interaction (the shell or window manager). None of those layers contains the logic of the others. The kernel does not know what a word processor does; it provides syscalls and the word processor brings its own logic.

Agience applies the same separation to knowledge work. **Artifacts** are the inodes: stable, addressable units with metadata, provenance, and content but no hardcoded type-specific behavior. **Workspaces** are scratch pads — fast, mutable, ephemeral, the place where draft thinking happens before anything is committed. **Collections** are versioned drives: immutable once written, auditable, the durable system of record. **Agents** are processes: they run tools, transform information, and produce outputs, but all durable truth is written back as first-class artifacts with explicit provenance. **MCP servers** are drivers: they own content-type-specific logic, deliver viewers, and expose tools to the kernel — none of which bleeds into the platform core. The window manager (the frontend Presentation layer) renders card chrome and manages layout without knowing anything about what each card contains.

---

## Three Layers

### Core (the kernel)

Core provides the platform's type-agnostic infrastructure: artifact CRUD, workspace lifecycle, collection lifecycle, commit orchestration, hybrid search (OpenSearch), S3 media storage, authentication, MCP plumbing, the event bus, and the type registry. Core is deliberately **type-blind** — it stores artifact content and context as opaque payloads and routes them to whoever owns that type. It never contains MIME type strings for vendor types, never parses `artifact.context` for specific fields, and never branches on content type. Its MCP server surface (`/mcp`) exposes roughly twelve generic tools to external clients such as VS Code and Claude Desktop. None of those tools are type-specific.

### Handlers (the drivers)

Handlers are the content-type-specific logic that Core deliberately does not know about. In Agience's architecture, handlers live **on MCP servers**, not in the platform. Each server owns one or more content types and provides: MCP tools (callable operations), HTML viewers served as `ui://` resources (rendered in sandboxed iframes), lifecycle hooks for the types it owns (on create, on commit), and the only code that ever parses `artifact.context` for its types. When the platform needs to display an artifact or invoke type-specific behavior, it resolves the handler through the registry and delegates across the MCP boundary. Adding a new content type means adding to a server — never touching Core.

### Presentation (the window manager)

The frontend is a type-oblivious shell. It renders card chrome (borders, titles, action buttons, window management, layout), manages the grid and floating windows, and hosts the sandboxed iframes that display server-provided viewers. All type-specific wiring flows through the registry — the frontend never imports handler code directly and never checks `if (contentType === 'something')`. A card displays whatever the iframe contains; the Presentation layer does not know or care what that is.

For the full layer spec including decision tests, violation inventory, and build plan, see [layered-architecture.md](layered-architecture.md).

---

## Database Architecture

Agience uses **ArangoDB** as its sole database for artifact storage.

**ArangoDB** holds both workspaces and collections. Workspace artifacts (the ephemeral, high-churn staging layer) can be freely edited, reordered, and discarded. This is where AI-produced content lands, where humans review and refine it, and where operators produce their drafts. Collection artifacts (the durable, versioned, immutable system of record) preserve history permanently once committed. ArangoDB's graph model supports the rich relationship structure that committed knowledge needs — cross-references, provenance links, grants, commit items. It also stores API keys, grants, and server credentials.

The **commit boundary** is the architectural key. Moving content from a workspace to a collection requires an explicit commit: a deliberate act that acknowledges human review and assigns provenance. If an LLM was involved anywhere in producing an artifact, that artifact is blocked from reaching a collection until a human has reviewed and approved it. The commit gate is enforced at the infrastructure level in Core's commit orchestration — it is not a convention that servers or clients can work around. This keeps AI-produced content in the draft layer until a human has signed off.

**OpenSearch** sits alongside both stores as the search projection: hybrid BM25 (lexical) and kNN (semantic, via OpenAI embeddings) with RRF fusion. Search results always route back to canonical artifacts — OpenSearch is an indexer, not a source of truth.

---

## MCP as the Integration Layer

Agience is MCP-native in both directions.

As an **MCP server**, Agience exposes its platform capabilities to external clients — VS Code, Claude Desktop, agent frameworks, CI pipelines. The server surface lives at `/mcp` (Streamable HTTP) and advertises itself via `/.well-known/mcp.json`. It provides roughly twelve purpose-driven tools organized by capability:

| Pillar | Tools |
|--------|-------|
| Knowledge & Research | `search`, `get_artifact`, `browse_collections`, `browse_workspaces` |
| Workspace Curation | `create_artifact`, `update_artifact`, `manage_artifact` |
| Analysis | `extract_information` |
| Commit | `commit_preview`, `commit_workspace` |
| Communication | `ask` |

Resources are exposed as `agience://` URIs covering collections and workspaces. All tools are generic — none are type-specific.

As an **MCP client**, Agience calls out to external MCP servers — both the first-party personas bundled with the platform and external vendor servers registered as artifacts. The client infrastructure lives in `backend/mcp_client/`. Browsers never call MCP servers directly; all server communication is proxied through Core.

The product rule for external integrations is **official-first**: if a vendor publishes an MCP server, Agience registers it as an artifact and proxies through it rather than rebuilding the vendor API. Agience-owned tools are reserved for platform-contextualized operations.

---

## First-Party Personas

Eight purpose-built MCP servers ship with the platform. Each is a standalone FastMCP process with its own Dockerfile, tools, and viewers. They are organized into three trust tiers based on their relationship with Core:

| Server | Tier | Domain |
|--------|------|--------|
| **seraph** | Kernel | Security, trust, secret decryption |
| **verso** | Kernel | Reasoning and transforms |
| **astra** | Platform | Ingestion, extraction, streaming |
| **atlas** | Platform | Governance and coherence |
| **nexus** | Platform | Routing and communication |
| **aria** | Application | Output, presentation, formatting |
| **sage** | Application | Research, retrieval, synthesis |
| **ophan** | Application | Finance and licensing |

All eight are mounted on a single unified host at `servers/_host/` (port 8082 in dev) on separate paths (`/aria/mcp`, `/sage/mcp`, etc.).

**All first-party servers** authenticate via `PLATFORM_INTERNAL_SECRET` — a shared secret that avoids the auth recursion problem and simplifies deployment. Third-party servers use the standard client credentials grant to exchange `client_id` + `client_secret` for a short-lived JWT. When Core proxies a user request to a server, it issues a delegation JWT (RFC 8693) with `sub=user_id` and `aud=server_client_id`; servers verify `aud` matches their own identity before accepting. All servers use the consolidated `AgieceServerAuth` class from `servers/_shared/agience_server_auth.py`.

For agent persona details, see [Solution Taxonomy](../overview/solution-taxonomy.md).

---

## Content Types

Every content type in Agience is a triple: a MIME type identity, an owning MCP server that provides tools and viewers, and an HTML viewer served as a `ui://` resource and rendered in a sandboxed iframe.

`application/vnd.agience.*` types are always Agience-authoritative and are defined on the first-party servers. Third-party `application/vnd.<vendor>.*` types are defined and served by the external MCP server that owns them. Standard MIME types (`text/*`, `image/*`, `application/json`, `application/pdf`, etc.) are handled by platform-provided default renderers — these are legitimate Core capabilities, not vendor handlers.

Type resolution is registry-driven:

```
Artifact has MIME type
  → Registry lookup
  → Owner (server) resolved
  → Viewer URL delivered to Presentation
  → Tool list available to agents
  → Context schema available to the handler (never to Core)
```

Presentation never imports handler code. It asks the registry for a viewer URL and hands it to the iframe sandbox host (`McpAppHost.tsx`). The registry is the seam between the type-oblivious shell and the type-aware handler.

For the content type system including `type.json` format, the `inherits` mechanism, and how types are registered, see [content-types.md](content-types.md).

---

## Key Design Principles

The following principles are non-negotiable. Every new line of code is tested against them before placement.

- **Type blindness in Core.** Core never contains MIME type constants for vendor types, never branches on content type, and never parses `artifact.context`. If a service would need to change when a new content type is added, it is in the wrong layer.

- **Handler owns its schema.** Only the MCP server that owns a content type may parse the internal structure of `artifact.context` for that type. Core passes context as opaque JSON. This boundary is the primary mechanism that prevents type-specific logic from leaking into the kernel.

- **No MIME constants in Core or Presentation.** The only MIME strings that appear in Core are the small set of kernel-known bootstrap types defined in `services/bootstrap_types.py` (e.g., `AUTHORITY_MIME`, `HOST_MIME`). All others belong on servers.

- **Registry as indirection.** All type-specific wiring — viewer, icon, provider, actions — flows through the registry. Presentation never imports from handler code. This is what allows the window manager to be type-oblivious.

- **LLM output never reaches a collection without human review.** Provenance is tracked at the infrastructure level. The commit gate in Core's orchestration checks `artifact.provenance.origin`. If the origin is `llm` or `composite` and no human has reviewed it, the commit is blocked. Servers and clients cannot override this.

---

## Further Reading

- [layered-architecture.md](layered-architecture.md) — full layer spec: decision tests, violation inventory, MCP Apps protocol alignment, build plan
- [content-types.md](content-types.md) — type definition format, registry, handler lifecycle
- [artifact-model.md](artifact-model.md) — artifact schema, state machine, reference model
- [security-model.md](security-model.md) — authentication, JWT shapes, API keys, grants, server credentials
- [Solution Taxonomy](../overview/solution-taxonomy.md) — agent persona designs (Aria, Astra, Atlas, Sage, Nexus, Ophan, Seraph, Verso)
- [Platform Overview](../overview/platform-overview.md) — product-level overview with implementation status markers
- [Information OS Analogy](../overview/information-os-analogy.md) — deeper treatment of the OS analogy for communicating Agience to stakeholders
