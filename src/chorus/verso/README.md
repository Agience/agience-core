# agience-server-verso

Status: **Reference** --- current server.py surface
Date: 2026-03-31

Verso is the reasoning and workflow persona. It currently exposes one synthesis path and one workflow runner, with additional orchestration tools declared but still stubbed.

## Current MCP Tools

Implemented paths:

| Tool | Description |
|---|---|
| `synthesize` | Synthesize information from multiple artifacts or raw input via the platform |
| `run_workflow` | Execute a workflow Transform inside a workspace |

Declared placeholders:

| Tool | Description |
|---|---|
| `chain_tasks` | Chain multiple tool calls sequentially |
| `schedule_action` | Schedule a deferred action |
| `evaluate_output` | Evaluate generated output quality |
| `submit_feedback` | Record training or review feedback |

## Configuration

- `AGIENCE_API_URI`
- `AGIENCE_API_KEY`
- `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `LOG_LEVEL`

## Running

```bash
pip install -r requirements.txt
AGIENCE_API_URI=http://localhost:8081 AGIENCE_API_KEY=your-key python server.py
```
