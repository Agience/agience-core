# Agience Backend

Status: **Reference**
Date: 2026-03-31

This directory contains the FastAPI backend for Agience Core: authentication, artifact CRUD, workspace and collection lifecycle, search, storage, and MCP infrastructure.

For the broader project map, use:
- `.dev/README.md` for internal developer documentation
- `docs/README.md` for public-facing docs
- `CLAUDE.md` and `backend/CLAUDE.md` for coding-agent guidance

## Layer Boundary

The backend is the Core platform layer. Keep it type-blind.

- Routers, services, and DB adapters should not hardcode content-type-specific behavior
- New domain behavior should generally live on persona servers under `servers/`
- Existing code in `backend/agents/` is legacy/in-transition; do not use it as a reason to add new type-specific logic to Core

Authoritative boundary rules live in `.dev/features/layered-architecture.md`.

## Directory Guide

```text
backend/
├── api/           # Pydantic request/response schemas by domain
├── core/          # Config, dependencies, embeddings, key management, event bus
├── db/            # ArangoDB and OpenSearch adapters
├── entities/      # Dual-context entity models and serialization helpers
├── mcp_client/    # Outbound MCP client infrastructure
├── mcp_server/    # Agience MCP server mounted at /mcp
├── routers/       # FastAPI routers; keep them thin and type-agnostic
├── schemas/       # Database initialization and schema loaders
├── search/        # Query parsing, weights, and hybrid search support
├── services/      # Core orchestration and platform services
├── tests/         # Pytest suites
└── main.py        # App entry point and lifespan wiring
```

## Request Flow

```text
HTTP request
  -> router
  -> api module
  -> service
  -> db/search/storage adapter
```

Routers should not call DB adapters directly.

## Key Surfaces

- `main.py` initializes FastAPI, CORS, startup schema loading, and router registration
- `mcp_server/server.py` exposes the public MCP tool surface
- `mcp_client/` handles outbound calls to external and first-party MCP servers
- `services/workspace_service.py` orchestrates workspace lifecycle and commit flow
- `services/collection_service.py` owns committed collection lifecycle and indexing hooks
- `services/agent_service.py` is the unified dispatch path for agent/operator execution

## Local Development

```bash
cd backend
python main.py
```

Recommended validation:

```bash
cd backend
ruff check .
pytest tests/
```

## Related Docs

- `.dev/features/layered-architecture.md`
- `.dev/features/artifact-model-and-referencing.md`
- `docs/mcp/overview.md`
- `.dev/testing/test-suite-summary.md`