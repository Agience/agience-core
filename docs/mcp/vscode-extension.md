# Agience in VS Code

Status: **Reference**
Date: 2026-04-01

VS Code supports MCP servers natively via its built-in MCP client. You can connect VS Code to Agience to search your knowledge base, browse workspaces and collections, create and update artifacts, and run AI-assisted operations — all from within your editor.

---

## Prerequisites

- VS Code 1.99 or later (native MCP client support)
- A running Agience instance (cloud or self-hosted)
- An Agience API key (create one in **Settings → API Keys**)

---

## Configuration

Add the Agience MCP server to your VS Code `settings.json`:

```json
{
  "mcp": {
    "servers": {
      "agience": {
        "type": "http",
        "url": "https://<your-agience-host>/mcp",
        "headers": {
          "Authorization": "Bearer <your-api-key>"
        }
      }
    }
  }
}
```

Replace `<your-agience-host>` with your Agience URL (e.g., `app.agience.ai` or `localhost:8081` for local dev) and `<your-api-key>` with your API key.

### Workspace-scoped configuration

To scope the connection to a specific project, add the same entry to `.vscode/settings.json` in your repository instead of your user settings.

---

## Storing your API key securely

Rather than putting the API key directly in `settings.json`, use VS Code's secret storage or an environment variable substitution:

**Using an environment variable:**
```json
{
  "mcp": {
    "servers": {
      "agience": {
        "type": "http",
        "url": "https://<your-agience-host>/mcp",
        "headers": {
          "Authorization": "Bearer ${env:AGIENCE_API_KEY}"
        }
      }
    }
  }
}
```

Set `AGIENCE_API_KEY` in your shell profile or a `.env` file that VS Code loads.

---

## What you can do

Once connected, the Agience MCP tools are available to any AI assistant in VS Code (GitHub Copilot, Continue, Cursor, etc.) that supports MCP.

### Available tools

| Category | Tool | Description |
|---|---|---|
| **Knowledge** | `search` | Hybrid search across workspaces and collections |
| | `get_artifact` | Retrieve a specific artifact by ID |
| | `browse_workspaces` | List workspaces and their artifacts |
| | `browse_collections` | List collections and their artifacts |
| **Curation** | `create_artifact` | Create a new artifact in a workspace |
| | `update_artifact` | Update an artifact's content or context |
| | `manage_artifact` | Archive, revert, or delete an artifact |
| **Analysis** | `extract_information` | Extract structured information from an artifact |
| **Communication** | `ask` | Grounded Q&A: search + LLM synthesis |

### Example prompts

**Search your knowledge base:**
> "Search my Agience workspace for documentation on the authentication flow"

**Create an artifact from code:**
> "Create an Agience artifact in workspace `ws_abc123` with the title 'API Auth Notes' and this content: ..."

**Extract structured information:**
> "Extract the action items from the meeting transcript artifact `art_xyz789`"

**Ask with grounding:**
> "Ask Agience: what are the key decisions made in Q1 around the data pipeline?"

---

## API key scopes

You can create a narrowly-scoped API key to limit what the VS Code connection can do.

In **Settings → API Keys**, create a key with scopes appropriate for your workflow:

| Scope | Access granted |
|---|---|
| `search:read` | Search and browse |
| `artifact:read` | Read artifact content |
| `artifact:write` | Create and update artifacts |
| `artifact:manage` | Archive, revert, delete |

A read-only key (`search:read`, `artifact:read`) is sufficient for most AI assistant use cases.

---

## Connecting to a local dev instance

For local development, set `url` to your local backend:

```json
{
  "mcp": {
    "servers": {
      "agience-local": {
        "type": "http",
        "url": "http://localhost:8081/mcp",
        "headers": {
          "Authorization": "Bearer <your-api-key>"
        }
      }
    }
  }
}
```

The local instance uses the same MCP transport and tool surface as the hosted version.

---

## Troubleshooting

**Connection refused:** Verify the Agience backend is running and the URL is correct.

**401 Unauthorized:** Check that the API key is valid and has not expired. Regenerate it in Settings → API Keys if needed.

**Tool not found:** Verify your Agience instance version supports the tool you're calling. Check `GET /.well-known/mcp.json` to see the advertised endpoint.

**Empty results from search:** Confirm that your API key has access to the workspaces and collections you're searching. Collection access requires a grant from the workspace owner.

---

## See also

- [MCP Client Setup](client-setup.md) — connecting other MCP clients to Agience
- [MCP Overview](overview.md) — Agience MCP server surface and tool reference
- [Security Model](../architecture/security-model.md) — API keys, scopes, and grants
