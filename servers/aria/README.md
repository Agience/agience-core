# agience-server-aria

Status: **Reference** --- current server.py surface
Date: 2026-03-31

Aria is the output and presentation persona. It formats artifacts for human consumption and serves viewer HTML as `ui://` resources.

## Current MCP Tools

Implemented paths:

| Tool | Description |
|---|---|
| `format_response` | Format content for human-facing delivery in markdown, HTML, or plain text |
| `present_card` | Prepare an artifact for presentation-ready output; legacy name pending rename |
| `run_chat_turn` | Run one agentic chat turn with tool-calling support for Aria-owned chat and presentation flows |

Declared placeholders:

| Tool | Description |
|---|---|
| `render_visualization` | Create charts or diagrams from structured data |
| `adapt_tone` | Reframe output for a target audience or tone |
| `narrate` | Produce natural-language narration from structured input |

## UI Resources

Aria currently serves viewer HTML for generic view, chat, presentation, and visualization artifact types from `servers/aria/ui/`.

## Configuration

- `AGIENCE_API_URI`
- `AGIENCE_API_KEY`
- `OPENAI_API_KEY` for `run_chat_turn`
- `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `LOG_LEVEL`

## Running

```bash
pip install -r requirements.txt
python server.py
```

See `.well-known/mcp.json` for the transport and discovery metadata.
