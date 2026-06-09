# Mantle — Claude Code Instructions

Status: **Reference**
Date: 2026-05-07

See root `CLAUDE.md` for vocabulary, architecture overview, and global rules.
Authoritative spec for the storage model: `.dev/features/universal-artifact-model.md`.

**This is the Mantle service** (FastAPI + Arango, port 8081). Mantle is the
type-blind artifact kernel. Identity, OIDC, grants, passkeys, OTP, API keys,
server credentials, and platform settings all moved to **Origin** (`origin/`)
in 1.1d. If you're looking for any of those services, edit `origin/`, not here.

Cross-service helpers Mantle uses to talk to Origin live in `mantle/clients/`
(`origin_client.py`, `jwks_client.py`). Shared Python (config, key_manager,
scopes, logging_utils) lives in top-level `kernel/` (under `src/kernel/`) —
both Origin and Mantle import from it as `from kernel import ...`.

---

## Stack

- **Python 3.11+**, FastAPI, Uvicorn (ASGI)
- **ArangoDB** — single source of truth for the unified artifact store
  (drafts + committed versions in one `artifacts` table)
- **Encrypted MANTLE + MANTLE-SSE** — in-process search over AES-256-GCM
  blobs in S3 (lexical via blind-token BM25; vector via encrypted IVF;
  fused via RRF). Replaced OpenSearch in Step 2.6.9 (2026-05-09).
- **S3-compatible** (MinIO locally, AWS in prod) — media/document
  storage *and* the encrypted MANTLE+SSE blobs
- **FastMCP** is no longer running inside Mantle. The MCP surface lives
  in Chorus's universal gateway; Mantle exposes HTTP REST only and uses
  `chorus_client` for outbound MCP. (See
  `.dev/features/mantle-mcp-consolidation.md`.)

---

## Storage Model — Unified Artifact Store

**One `artifacts` table. One `collections` table. No workspace/collection split.**

A workspace is a `Collection` with `content_type == "application/vnd.agience.workspace+json"`.
Drafts and committed snapshots live in the same `artifacts` table, distinguished by `state`:

| `state` | Meaning |
|---------|---------|
| `draft` | Mutable. Visible to anyone with access to the collection. |
| `committed` | Immutable snapshot. New committed versions append (versioning). |
| `archived` | Soft-deleted. Restorable. |

**Commit = state flip.** A `draft` becomes `committed` via a single AQL `UPDATE state='committed'`. No record creation, no cross-table copies, no membership delta. The 800-line dual-store commit collapsed to ~50 lines.

**Edges hold ordering and access topology.** `collection_artifacts` edges point to `artifacts/{root_id}` (the stable root document) and carry `order_key` (base-62 fractional index), `origin` (bool — creation edge vs link), `propagate` (CRUDEASIO action list controlling grant inheritance), and `relationship` (e.g. `"operator"` for non-containment edges). Reordering touches one edge; the artifact docs are never rewritten.

**Resolution.** Listing a collection traverses its edges, then for each `root_id` resolves to the draft (preferred) or the latest committed version in the same collection — see `db.arango.list_collection_artifacts`.

**Access control.** Grant `resource_type` is canonically `"artifact"` (not `"collection"`). `created_by` is provenance only — it does NOT imply ownership or access. All access requires explicit GrantEntity records with CRUDEASIO flags. Grants inherit through origin edges: the light-cone traversal walks parent origin edges, intersecting each edge's `propagate` mask with the requested action.

---

## Directory Structure

```
mantle/
├── api/             # Domain-organized request/response schemas
├── clients/         # Cross-service HTTP clients (origin_client, jwks_client)
├── db/
│   └── arango.py            # Unified artifact + edges CRUD
├── entities/
│   ├── artifact.py          # Single Artifact entity (draft/committed/archived)
│   ├── collection.py        # Single Collection entity (with content_type)
│   └── ...
├── routers/         # FastAPI route handlers (Origin-moved routers are gone)
├── schemas/arango/  # Collection + index init
├── search/          # Encrypted MANTLE + MANTLE-SSE engine + commit-path indexer
│   └── →      # MANTLE vector + SSE lexical packages
├── services/        # Business logic (workspace_service, collection_service, …)
│                    # person_service is an HTTP shim to Origin;
│                    # chorus_client is the only MCP egress path (no in-process MCP client)
├── tests/           # pytest test suite
└── main.py
```

---

## Request Flow

```
HTTP request
  → router (validates, delegates)
  → service (business logic, orchestration)
  → db adapter (ArangoDB) or storage adapter (S3 for encrypted search blobs)
```

**Never call DB adapters directly from routers.**

---

## Services Reference

| Service | Responsibility |
|---------|----------------|
| `workspace_service.py` | Collection-scoped artifact CRUD + commit (the entire artifact lifecycle, not just workspaces) |
| `collection_service.py` | Collection CRUD, grant-aware reads, vector indexing after commit |
| `auth_service.py` | JWT creation/verification (RS256) |
| `content_service.py` | S3 presigned URLs, signed downloads, file cleanup |
| `dependencies.py` | FastAPI auth dependencies + the unified `check_access(auth, artifact_id, action, db)` |
| `bootstrap_types.py` | Kernel-known-at-init MIME constants |
| `secrets_service.py` | Encrypted credential storage (Fernet) |
| `chorus_client.py` | Outbound MCP JSON-RPC to Chorus's universal gateway (`call_tool`, `read_resource`, `list_capabilities`) |
| `mcp_resource_importer.py` | Native `dispatch_resources_*` hooks for the `vnd.agience.mcp-server+json` type — capability materialization into Arango |
| `person_service.py` | Person/user lifecycle, first-login provisioning |
| `types_service.py` | Content-type resolution from `types/` |
| `seed_provisioning/` | Declarative bootstrap. `loader.py` (`seed_from_artifacts`) applies the seed files under `package/seeds/{platform,user,admin}/` as artifacts/edges/grants; `user_provisioning.py` is the thin per-user runtime glue (inbox workspace + materialization); `exporter.py` is the inverse (`export_collection` → seed dicts). The old imperative seeders are gone. See `.dev/features/declarative-bootstrap-artifacts.md`. |
| `platform_topology.py` | Host/server/tool topology resolution |
| `operation_dispatcher.py` | Type-declared `operations.{op}` dispatch |
| `handler_registry.py` | Native handler registry for `dispatch.kind: native` |

---

## Entity Design

**Single serialization. No dual `to_dict_workspace()` / `to_dict_collection()` methods.**

| Entity | Purpose |
|--------|---------|
| `Artifact` | Unified artifact. Fields: `id`, `root_id`, `collection_id`, `context`, `content`, `state`, `created_by/time`, `modified_by/time`, `name`, `description`, `content_type`. First version: `id == root_id`. Any artifact can have children (universal container model). All addressing by UUID — slugs are type-owned context only. |
| `Collection` | Alias for `Artifact`. Container artifact distinguished by `content_type` (workspace or collection). |
| `Grant` | CRUDEASIO grant on an artifact (`resource_type: "artifact"`). 9 flags: C, R, U, D, E, A, S, I, O. |
| `Commit` / `CommitItem` | Provenance for a state flip. |
| `APIKey`, `ServerCredential`, `Person` | Identity-tier entities. |

**ArangoDB conventions:**
- `_key` = document identifier (= entity `id`)
- `_id` = `{collection_name}/{_key}` — never use where `_key` is expected
- Edge collection `collection_artifacts`: `_from = artifacts/{cid}`, `_to = artifacts/{root_id}`, plus `order_key`, `origin`, `propagate`, `relationship`

---

## Routers Reference

Mantle's router surface (post 1.1d Origin extraction). Auth, identity, grants,
passkeys, OTP, API keys, server credentials, platform admin, and setup wizard
all moved to `origin/routers/`.

| Router | Scope |
|--------|-------|
| `artifacts_router.py` | Generic artifact CRUD + invoke (`POST /artifacts/{id}/invoke`) + search + upload + children + `op/{op_name}` dispatch (commit, revert, and all lifecycle ops). Type-blind kernel surface — Step 1.6 slimmed this from 21 endpoints to ~15. |
| `events_router.py` | Unified `/events` WebSocket — multiple filtered subscriptions per connection |
| `secrets_router.py` | Secret CRUD (encrypted at rest, kernel-level storage) |
| `server_credentials_router.py` | Reads JWK key uploads for MCP server cred encryption (CRUD itself is on Origin) |
| `types_router.py` | Content-type definitions from `types/` and `chorus/*/ui/` |
| `downloads_router.py` | Static `/relay/download` redirect for desktop-relay installer binaries (the WebSocket lives on Chorus) |
| `gate_router.py` | Internal kernel-server-only gate enforcement (entitlement checks) |

**Operation dispatch:** Every artifact type declares an `operations` block in its `type.json`. `operation_dispatcher.dispatch(op_name, artifact, body, ctx)` resolves the operation, enforces grants, fires `before` events, runs the registered handler (`mcp_tool` / `native` / `artifact_crud`), fires `after`/`error` events, returns the result. See `.dev/features/operations-schema.md`.

---

## Agent Architecture

- **Agents are artifacts** addressed by UUID. Canonical endpoint: `POST /artifacts/{id}/op/invoke`.
- **Operation dispatch**: `operation_dispatcher` resolves the artifact's `type.json` operations block and dispatches to whichever handler kind it declares (`mcp_tool`, `native`, `artifact_crud`, future `agent_runtime`). Agent execution lives in handlers — Mantle's kernel does not embed agent logic.
- **Identity**: always from auth token, never body.
- **No separate agent router**: `agents_router.py` is removed. All execution flows through `artifacts_router.py`.

---

## MCP Architecture

Mantle publishes **no MCP surface**. The MCP protocol — auth handshake,
JSON-RPC framing, tool schemas, server-info, capability negotiation — lives
only in Chorus's universal gateway. Mantle exposes HTTP REST only; clients
that want MCP go through `chorus.example.com/{server_artifact_id}/mcp`.

- The agent-facing artifact-management tool surface lives in chorus's
  `core` persona (`src/chorus/core/server.py`) — curated tools that proxy
  to Mantle's HTTP REST API.
- External MCP servers are still registered as `vnd.agience.mcp-server+json`
  artifacts, addressed by UUID through chorus's gateway.
- See `.dev/features/mantle-mcp-consolidation.md` for the full migration.

---

## Authentication

- RS256 JWT tokens — key pairs managed by `kernel/key_manager.py`
- Authority manifest at `KEYS_DIR/authority.manifest.json` carries inline JWKS for every trusted peer (origin / mantle / chorus). No HTTP `/.well-known/jwks.json` fetch.
- Scoped API keys for third-party MCP servers/agents — used directly on endpoints
- Server credentials (client_credentials grant) for third-party MCP server identity via `POST /auth/token`
- First-party kernel services (origin, mantle, chorus) authenticate to each other via mutual service JWTs signed with their own keypair (`<service>.private.pem`). No shared secret.
- Delegation JWTs (RFC 8693) for Mantle → persona server proxy with `act.sub` actor

**`check_access(auth, artifact_id, action, db)` — light-cone traversal:**
1. Fetch artifact doc. `created_by` is provenance only — no owner fast-path.
2. Direct grants on the artifact (`resource_type: "artifact"`, deny-before-allow).
3. Walk origin edges upward (max 10 levels). At each parent: intersect edge `propagate` mask with the requested action; if allowed, check grants on that parent. Stop on mask mismatch or no more origin parents.

No workspace special-casing, no `_CASCADING_ACTIONS`, no `resource_type: "collection"`.

---

## Content & File Storage

- Small text files (<128KB) → stored in `artifact.content`
- Large/binary files → S3 via presigned PUT
- S3 key pattern: `{tenant}/{artifact_id}.content`
- **All metadata lives in `artifact.context`** — including `content_key`, which `delete_artifact` reads directly (no recomputation)
- Content URL flow: `GET .../content-url` → signed inline URL (5-min expiry)

---

## Search

- `POST /search` — unified across all collections (workspaces and otherwise)
- Hybrid BM25 + kNN with RRF fusion (k=60)
- Embeddings via the shared `kernel/embeddings.py` — provider-agnostic HTTP. Default: Agience embeddings server (`EMBEDDINGS_URI`); when unconfigured, search degrades to BM25-only.
- Field boost presets in `mantle/search/weights/*.json`
- Both draft and committed artifacts are indexed; the `state` field allows filtering
- Re-indexing triggered after commit in `workspace_service.commit_workspace_to_collections`

---

## Configuration

Config resolution order (highest precedence first):
1. `.env.local` — local dev + pytest overrides
2. `.env` — Docker / shared defaults

Functionally required at runtime: `ANTHROPIC_API_KEY` (or another configured LLM provider key), `EMBEDDINGS_URI` (Agience embeddings server), `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`. Embeddings can be omitted in dev — search will degrade to BM25-only.

---

## Testing

```bash
cd backend
ruff check .
pytest tests/
```

**Rules:**
- Never write to real ArangoDB/S3 in tests
- Mock at the service or `db.arango`/`db.arango_identity` layer; use FastAPI `Depends()` overrides for auth + DB
- Mock all external HTTP calls
- Router tests required for every new/changed endpoint
- Unit tests required for non-trivial service/agent/search logic

**Test file patterns:**
```
mantle/tests/
├── test_router_*.py     # HTTP endpoint tests
├── test_service_*.py    # Business logic unit tests
└── conftest.py
```

---

## Fractional Ordering

`collection_artifacts` edges carry an `order_key` (base-62 lexicographic). Helpers live in `db/arango.py`:

- `after_key(prev) -> str` — pick a key strictly greater than `prev`
- `mid_key(a, b) -> str` — pick a key strictly between `a` and `b`
- `reorder_collection_artifacts(db, cid, ordered_root_ids)` — bulk reassign

Frontend sends reordered IDs via `PATCH /artifacts/{container_id}/order`.

---

## Key File Reference

| File | Purpose |
|------|---------|
| `main.py` | App init, CORS, router registration, lifespan DB init |
| `kernel/config.py` | Env var resolution (shared module under `src/kernel/`) |
| `kernel/dependencies.py` | DB session factory (`get_arango_db`) |
| `services/dependencies.py` | Auth dependencies (`get_auth`, `get_person`, `check_access`, `require_platform_admin`) |
| `services/workspace_service.py` | Artifact lifecycle: CRUD + commit + upload helpers |
| `services/collection_service.py` | Collection CRUD + grant-aware reads + vector indexing |
| `db/arango.py` | Unified artifact + collection + edges + grants + commits CRUD; fractional-index helpers |
| `db/arango_identity.py` | Person, platform_settings, passkey, OTP repos |
| `entities/artifact.py` | Unified `Artifact` entity |
| `entities/collection.py` | `Collection` entity (with `WORKSPACE_CONTENT_TYPE` constant) |
| `schemas/arango/initialize.py` | Collection + index init, `migrate_unified_artifact_store` |
| `services/chorus_client.py` | Outbound MCP JSON-RPC to Chorus's universal gateway |
