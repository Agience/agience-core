# Chorus — Claude Code Instructions

Status: **Reference**
Date: 2026-05-07

See root `CLAUDE.md` for vocabulary, architecture overview, and global rules.

This directory was renamed `servers/` → `chorus/` in Step 1.5 of the
four-container migration (2026-05-07). Path references inside still say
"servers" in some places — those are doc strings, not import paths.

---

## What Chorus Is

Chorus is the eight first-party MCP persona servers (Aria, Sage, Mantle,
Iris, Astra, Verso, Seraph, Ophan), unified into a single `_host` mount on
port 8082. Built into the `agience-chorus` image. Each server:
- Defines its own artifact types (via the content type system)
- Exposes MCP tools and resources
- Optionally defines frontend UI components for its content types
- Optionally defines workflow artifacts (Transform artifacts)

Servers are standalone — deploy only what you need. They are not plugins injected into the backend; they are independent MCP servers that the platform connects to as `vnd.agience.mcp-server+json` artifacts.

---

## The Eight Platform Servers

| Server | Domain | Purpose |
|--------|--------|---------|
| **Astra** | Ingestion | File ingestion, validation, indexing, live streaming |
| **Sage** | Research | Grounded Q&A, evidence synthesis, retrieval |
| **Mantle** | Governance | Decision logging, constraint tracking, coherence |
| **Verso** | Reasoning | Synthesis, workflow automation, transformation |
| **Aria** | Output | Response formatting, presentation, systems analysis |
| **Iris** | Networking | Message routing, comms planes, connectivity |
| **Seraph** | Security | Guardrails, policy enforcement, trust |
| **Ophan** | Economics | Accounting, financial artifact management, economies and emergent systems |

---

## Server Directory Structure

Each server follows this pattern:

```
servers/<server-name>/
├── server.py            # FastMCP app — tool and resource definitions
├── pyproject.toml       # Python package definition
├── requirements.txt     # Dependencies
├── ui/                  # Server-owned content type definitions + viewers
│   └── application/
│       └── vnd.agience.<type>+json/
│           ├── type.json    # Type identity + "ui" key for display metadata
│           └── view.html    # Viewer HTML (served as ui:// resource)
├── .well-known/         # Server metadata (mcp.json, server identity)
└── tests/               # Server test suite
```

---

## Adding a New Tool

Tools are defined as decorated async functions in `server.py`:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("server-name")

@mcp.tool()
async def my_tool(
    workspace_id: str,
    artifact_id: str,
    input: str,
    ctx: Context
) -> str:
    """
    Clear description of what this tool does.

    Args:
        workspace_id: The workspace to operate in
        artifact_id: The artifact to operate on
        input: User input or query
    """
    # Tool implementation
    ...
```

**Tool naming conventions:**
- Use snake_case
- Name by action + subject: `ingest_file`, `search_artifacts`, `log_decision`
- Organize by capability pillar (not CRUD)

**Tool design rules:**
- Tools should be platform-contextualized (workspace_id, artifact_id, user identity)
- Never re-implement what an official vendor MCP server provides
- Tool descriptions are the primary interface for LLMs — write them clearly and precisely
- Parameters should be typed and documented in the docstring

---

## Adding a New Resource

```python
@mcp.resource("agience://workspaces/{workspace_id}/artifacts")
async def list_artifacts(workspace_id: str) -> list[dict]:
    """List all artifacts in a workspace."""
    ...
```

Resources use `agience://` URI scheme. They are read-only data surfaces.

---

## Content Type Integration

If a server defines new artifact types, add them to:
1. `servers/<server-name>/ui/application/vnd.agience.<type>+json/type.json` — type definition (includes `"ui"` key for display metadata)
2. `servers/<server-name>/ui/application/vnd.agience.<type>+json/view.html` — viewer HTML (optional, for types with a visual representation)

Register viewers as `@mcp.resource` handlers using the `ui://` URI scheme:

```python
@mcp.resource("ui://<server-name>/vnd.agience.<type>.html")
async def my_type_viewer_html() -> str:
    view_path = pathlib.Path(__file__).parent / "ui" / "application" / "vnd.agience.<type>+json" / "view.html"
    return view_path.read_text(encoding="utf-8")
```

New types should inherit from platform primitives where possible:

```json
// type.json
{
  "mime": "application/vnd.agience.research+json",
  "version": 1,
  "inherits": ["application/json"],
  "description": "A research summary artifact",
  "ui": {
    "label": "Research",
    "icon": "search",
    "color": "#0ea5e9",
    "viewer": "research"
  }
}
```

---

## Authentication

Servers authenticate to the Agience platform using API keys registered as `vnd.agience.key+json` artifacts. The API key is included as a Bearer token in MCP requests.

API key scope format: `resource|tool|prompt : mime : action [: anonymous]`

When a server calls back into the Agience MCP endpoint (`/mcp`), it passes its API key. The ASGI auth middleware validates it per-request.

---

## Server Registration

External servers (including platform servers in production) are registered in the Agience workspace as `vnd.agience.mcp-server+json` artifacts. Mantle's `chorus_client` issues JSON-RPC calls into Chorus's universal gateway, which routes by the artifact's `kind` (persona / external / relay).

Local development: servers can be run directly and registered via the Agience UI or API.

---

## Testing

```bash
cd servers/<server-name>
pytest tests/
```

**Rules:**
- Mock external platform calls (don't hit real Agience backend in unit tests)
- Test tool output shapes, not implementation details
- Integration tests should use a local Agience stack

---

## `.well-known/mcp.json`

Each server must publish discovery metadata:

```json
{
  "name": "agience-<server-name>",
  "version": "1.0.0",
  "endpoints": {
    "streamable_http": "/mcp"
  },
  "tools": ["tool_name_1", "tool_name_2"]
}
```

---

## Key Patterns

- Use `async def` for all tools and resources
- Inject context (`ctx: Context`) for logging and progress
- Return structured dicts or typed objects — avoid raw strings for complex results
- Use `artifact_id` references for cross-artifact relationships — never embed artifact content inline
- Transform artifacts (`vnd.agience.transform+json`) define reusable workflows — prefer them over hardcoded agent flows
