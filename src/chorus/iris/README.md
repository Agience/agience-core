# agience-server-nexus

Status: **Reference** --- current server.py surface
Date: 2026-03-31

Nexus is the networking and transport persona. It handles delivery channels, webhooks, sandboxed shell execution, and the scaffolding for endpoint and tunnel routing.

## Current MCP Tools

Implemented paths:

| Tool | Description |
|---|---|
| `send_email` | Send an email via the configured delivery path |
| `send_message` | Send a prepared message via a registered channel adapter |
| `get_messages` | Poll a channel for new messages since a cursor |
| `list_channels` | List registered channel adapters |
| `create_webhook` | Register an inbound webhook and return its endpoint URL |
| `exec_shell` | Execute a command inside the Nexus sandbox |

Declared placeholders:

| Tool | Description |
|---|---|
| `health_check` | Check health of a remote endpoint |
| `list_connections` | List registered service connections |
| `register_endpoint` | Register an endpoint for routing |
| `route_request` | Route a request through a registered endpoint |
| `tunnel` | Open a secure relay tunnel |
| `proxy_tool` | Proxy an MCP tool call through a registered endpoint or tunnel |

## Security Notes

`exec_shell` is sandboxed to `NEXUS_CWD` and rejects path traversal. Optional authorizer artifact settings are available for additional policy checks.

## Configuration

- `AGIENCE_API_URI`
- `AGIENCE_API_KEY`
- `NEXUS_CWD`
- `NEXUS_AUTHORIZER_ARTIFACT_ID`
- `NEXUS_AUTHORIZER_WORKSPACE_ID`
- `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `LOG_LEVEL`

## Running

```bash
pip install -r requirements.txt
AGIENCE_API_URI=http://localhost:8081 AGIENCE_API_KEY=your-key python server.py
```
