# Agience as an Information OS (Filesystem Analogy)

Status: **Reference**
Date: 2026-04-01

This doc explains Agience's architecture using a familiar mental model: **an operating system + filesystem**. The goal is not to claim POSIX semantics; it's to communicate why the platform is safe, scalable, and composable for enterprise AI workflows.

> **Design principle:** Humans look at Cards. Agents look at Artifacts.

---

## One-paragraph version

Agience works like an **information operating system**: artifacts are the platform's "inodes" (stable identities + metadata + permissions + history), content types are "file associations" (how each thing behaves and which viewer/actions apply), object storage (S3-compatible) is the "disk" for large bytes, and search is the "indexer" that accelerates retrieval without becoming the source of truth. Agents and MCP tools act like processes and drivers: they can transform and route information, but all durable truth is written back as first-class artifacts with explicit access control and auditability. Cards are the human-facing windows that display artifacts --- the UI layer, not the data layer.

---

## Why this analogy fits

Enterprises need AI systems to behave like production infrastructure:
- stable object identities
- explicit access boundaries
- predictable composition of tools
- durable history
- fast retrieval that doesn't rewrite truth

Agience's architecture intentionally separates:
- **system of record** (Workspaces + Collections)
- **content bytes** (object storage)
- **projections** (search indices)
- **compute/extension plane** (agents + MCP servers)

This is exactly the separation an OS/filesystem provides: inode table + blocks + indexers + processes/drivers.

---

## Mapping: Agience to filesystem concepts

### Storage and identity

- **Artifact (workspace/collection) -> inode / file record**
  - An artifact is the stable identifier and metadata container: title, tags, context, provenance, links.
  - Like an inode, it can exist independently of where the bytes are stored.
  - A Card is the UI window that displays this artifact to a human.

- **Artifact `content` (small text) -> small file payload**
  - Inline text is optimized for fast editing and LLM access.

- **S3-compatible content (`{tenant}/{artifact_id}.content`) -> disk blocks / object store**
  - Large/binary bytes live outside the DB.
  - The DB remains a fast metadata/index and transaction layer, not a blob store.

- **Derivatives (`.thumb`, `.preview`, etc.) -> derived files / sidecars**
  - Like OS-generated thumbnails or preview caches.

### Behavior and UX

- **Content types (MIME + registry) -> file extensions + OS associations**
  - Content type determines how an artifact opens, renders, and what actions apply.
  - The registry acts like the OS "open with..." table and capability model.

- **Views/Containers -> folders, shortcuts, saved searches**
  - Agience is not limited to one hierarchy. A single artifact can appear in multiple views.
  - Closest analogy: tags + saved searches + shortcuts, not just directories.

### Trust boundary and durability

- **Workspace -> Commit -> "save + publish to system-of-record"**
  - Workspaces are the high-churn scratch area.
  - Commit promotes reviewed artifacts to durable history.
  - Closest analogy: staging -> snapshot -> publish.

---

## Mapping: Agience to operating system concepts

- **Agents/operators -> processes/jobs**
  - They take inputs, call tools, produce outputs.
  - They generate explicit artifacts (e.g., answer/evidence) with receipts/provenance rather than ephemeral chat.

- **MCP servers -> drivers / external services behind system calls**
  - Agience doesn't load arbitrary third-party code into the core backend.
  - Instead, it calls explicit tool interfaces across a boundary.

- **Scoped grant tokens -> capability-based access control**
  - Instead of ambient access, keys grant explicit capabilities (what resource/tool actions are allowed).

- **Receipts / provenance -> job logs + audit trail**
  - "What ran, on what inputs, producing what outputs" is the operational truth.

---

## Search: the filesystem indexer analogy

- **OpenSearch index -> OS indexer (Spotlight/Windows Search)**
  - Record information with accurate **context**
  - Semantic Ontology aligns to human observation behavior.
  - Always on, always detailed.

- **Hybrid retrieval (lexical + semantic) -> keyword index + semantic assist**
  - Search **context**, not **content**.
  - Results still route back to canonical artifacts.
  - Semantic Ontology aligns to human recall process.

---

## The dual-surface model

Unlike a traditional filesystem where files are accessed through a single interface, Agience provides two surfaces for the same underlying data:

| Surface | Consumer | Interface | Analogy |
|---|---|---|---|
| **Cards** | Humans | React UI components | Windows/Finder --- visual, interactive |
| **Artifacts** | Agents, MCP clients, API | REST API + MCP tools | CLI/syscalls --- programmatic, structured |

Both surfaces operate on the same stored entity. The artifact is the inode; the card is the window. This separation ensures agents get clean structured data while humans get rich visual presentation.

---

## Benefits

- **Safety through boundaries**
  - Draft vs durable truth is explicit. AI can assist broadly without silently becoming the system of record.

- **Scales for real data**
  - Metadata and transaction semantics stay in DB; large bytes live in object storage with signed access.

- **Composable by design**
  - Tools and integrations are enumerated interfaces (MCP), which is easier to govern than arbitrary plugins.

- **Auditability is structural**
  - Durable artifacts, version history, and receipts/provenance make it easier to defend outputs in regulated environments.

- **Multiple views over the same truth**
  - Instead of copying content into many artifacts, you render different views from shared units.

---