# Local Server Definitions

Status: **Reference**
Date: 2026-03-31

Place preapproved local MCP server definitions here as JSON files.

Each file should contain a single object like:

```json
{
  "server_id": "local-example",
  "label": "Local Example Server",
  "command": ["python", "server.py"],
  "cwd": "C:/path/to/server",
  "env": {
    "MCP_PORT": "9100"
  }
}
```

Only servers defined here can be started or stopped through the desktop host runtime.