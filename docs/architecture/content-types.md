# Content types

Status: **Reference**
Date: 2026-04-01

---

## Overview

Every Agience content type is a triple: a MIME identity, a backend MCP server that owns
the runtime behavior, and a frontend viewer that presents the artifact to a human. The
platform's role is to be the message bus and permission layer between these three things.
It does not implement content logic — it routes.

```
MIME type string     →  the identity and contract
MCP server           →  the backend: tools, lifecycle hooks, AI behavior
Frontend viewer      →  the presentation: React component or isolated handler
```

This model is analogous to how an operating system dispatches file types to registered
applications — but applied at the browser + MCP protocol layer, where handlers are
networked, AI-native, and composable across any language or runtime.

---

## What a content type is

A content type is an **addressable MIME identity with a registered set of capabilities**.

The MIME string (`application/vnd.agience.chat+json`, `application/vnd.acme.recipe+json`,
etc.) is the identity claim. It is not a capability by itself. A MIME string means nothing
inside an Agience instance unless that instance has a registered handler for it.

The full contract has three facets:

### 1. Type semantics

Declared in `type.json` (and optionally `presentation.json`) under the `types/` directory
or a server's `ui/` subtree. This answers:

- What MIME string identifies this type?
- What does it inherit from (for wildcard fallback resolution)?
- What are the default label, icon, display modes, and affordances?

### 2. Frontend implementation

One or more viewer implementations that render an artifact of this type in the platform UI.
A single type may have distinct implementations for different UX surfaces (a floating window
viewer, an inline grid card, an admin control plane, a public embed). Implementations
declare how they are delivered and what host capabilities they require.

### 3. Backend lifecycle handlers

An MCP server that the platform calls at known points in the artifact lifecycle. Domain-
specific tools exposed by that server become available to the chat agent automatically
whenever an artifact of this type is open.

---

## Ownership model

### Agience-authoritative types

MIME types in the `application/vnd.agience.*` tree are always Agience-authoritative. Their
type definitions, viewers, and MCP servers are maintained by the Agience project. First-
party implementations live under `servers/<name>/ui/` and are deployed as standalone
FastMCP processes.

No third party may register a competing handler for a `vnd.agience.*` type on a given
instance without that instance's operator explicitly allowing it.

### Vendor types

MIME types in the `application/vnd.<vendor>.*` tree belong to the vendor that declares
them. A vendor ships their type definition, MCP server, and frontend viewer as a
distributable unit. The Agience instance operator registers the vendor's server as a
`vnd.agience.mcp-server+json` artifact, after which the platform treats it like any
other registered server.

### Standard MIME types

Platform builtins handle standard MIME types (`text/plain`, `text/markdown`,
`application/json`, `image/*`, `audio/*`, `video/*`, `application/pdf`). These are
legitimate platform-layer capabilities, not content-type handlers in the vendor sense.
They are always available without any server registration.

---

## How types are served

### Type definitions

Type metadata is discovered at build time from two sources:

- `types/<category>/<subtype>/type.json` — platform builtins and Agience-authoritative
  skeleton definitions
- `servers/<name>/ui/<category>/<subtype>/type.json` — first-party server-owned definitions

Each `type.json` carries the MIME string, inheritance chain, version, and a `"ui"` key
with display metadata. An optional `presentation.json` carries viewer keys, modes, states,
and provider declarations. An optional `frontend.json` carries the full implementation
manifest for multi-plane resolution.

### Viewers as `ui://` resources (target architecture)

In the target model, a server advertises its viewer bundles as `ui://` resources via the
MCP Apps protocol. The platform fetches and mounts viewers at runtime without a core
rebuild. The viewer communicates with the host through the `agience-card-v1` bridge API,
which provides typed access to workspace context, artifact mutation, and agent invocation
without exposing host internals.

During the current phase, first-party viewers are compiled into the platform build (the
`bundled` delivery kind). The bridge API and isolation infrastructure are in place so the
migration to runtime-loaded viewers is a delivery change, not an architectural one.

---

## Trust model

### Trust levels

| Level | Who | How installed | Sandbox |
|---|---|---|---|
| **Platform builtin** | Standard MIME renderers | Always available | None |
| **First-party** | Agience-owned `vnd.agience.*` servers | Built in or deployed with the instance | None |
| **Self-published** | Instance operator's own servers | Registered as a server artifact (manual) | None — operator trusts their own code |
| **Community / trusted third-party** | Known authors | Registered as a server artifact (manual, with review) | Capability review at install time |
| **Untrusted third-party** | Unknown authors | Not supported without full Worker isolation | Worker-based JS sandboxing (future) |

### MIME authority vs handler trust

The MIME string is an identity claim, not an authorization. Any server can declare a
handler for any MIME string, but that declaration has no effect inside a specific Agience
instance unless the instance operator has registered that server. The trust anchor is
the registered server artifact, not the MIME string.

This is the same model as VS Code extensions or browser extensions: a handler the operator
willingly registers gets scoped access to the workspace. Mitigations follow the same
pattern — signed packages, a curated registry, and capability declarations that the
operator must approve before installation.

### What a registered server can access

A registered type server can call back into the platform's own MCP server (`/mcp`) to:

- search workspaces and collections
- read, create, and update artifacts
- browse workspaces and collections
- invoke LLM inference via the user's BYOK key and model preference (planned)

The type server never holds API keys. The platform mediates all access, scoped to the
workspace the artifact lives in. A type server cannot reach outside what the platform
explicitly exposes through this surface.

---

## Where type definitions live

### Builtin and skeleton definitions

```
types/
  application/
    vnd.agience.chat+json/
      type.json
      presentation.json
    json/
      type.json
  text/
    markdown/
      type.json
  image/
    _wildcard/
      type.json
  ...
```

The `_wildcard` directory name is a sentinel that matches any subtype under that top-level
MIME category (e.g. `image/*` matches `image/png`, `image/jpeg`, etc.).

### First-party server definitions

```
servers/
  aria/
    ui/
      application/
        vnd.agience.chat+json/
          type.json
          presentation.json
          frontend.json    ← optional multi-plane implementation manifest
          view.html        ← iframe-delivered viewer (target architecture)
  ophan/
    ui/
      application/
        vnd.agience.license+json/
          type.json
          presentation.json
          frontend.json
```

The server `ui/` subtree mirrors the `types/` layout exactly. When a type appears in both
locations, the server definition extends or overrides the skeleton definition.

---

## The MCP server contract

A type's MCP server may implement any of the following lifecycle tools. They are called
by the platform at known points in the artifact lifecycle. All are optional — unimplemented
tools are silently skipped.

| Tool | When called |
|---|---|
| `on_create` | An artifact of this type is created |
| `on_open` | An artifact is opened in a viewer |
| `extract_text` | An artifact is committed (for search indexing) |
| `summarize` | An artifact is requested for LLM context injection |

Domain-specific tools (e.g. `scale_recipe`, `generate_insights`) are exposed alongside
lifecycle tools and appear in the chat agent's tool surface automatically whenever an
artifact of this type is open in the active workspace.

---

## Installation

Content type servers are installed on a per-instance basis as `vnd.agience.mcp-server+json`
artifacts. The intended flow for the host artifact (the instance's execution boundary):

1. Open the host artifact for the current runtime.
2. Add a server artifact pointing to the server's endpoint.
3. The platform fetches the server manifest, registers the server, and loads its viewer.

No CLI, no restart, no config file edits. The authority artifact is the domain and
governance root; the host artifact is the runtime switchboard; server artifacts are the
host's configurable children.

Until the desktop-host relay is fully operational, this flow is the target UX. In practice
today, server registration is handled at instance provisioning time by an operator.

---

## See also

- [Content-type registry](../features/content-type-registry.md) — how the registry works and how to register a new type
- [MCP overview](../mcp/overview.md) — MCP server and client architecture
- [Layered architecture](layered-architecture.md) — Core / Handler / Presentation boundary rules
- [Artifact model](artifact-model.md) — artifact structure and context schema
- [Information OS analogy](../overview/information-os-analogy.md) — the OS/filesystem mental model
