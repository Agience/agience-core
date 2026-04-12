# agience-server-astra

Status: **Reference** --- current server.py surface
Date: 2026-03-31

Astra is the ingestion persona. It brings external content into Agience, derives artifact text when needed, and owns the live-streaming ingestion path.

## Current MCP Tools

Implemented paths:

| Tool | Description |
|---|---|
| `ingest_file` | Ingest raw text or a file URL into a workspace as an artifact |
| `document_text_extract` | Extract text from a PDF artifact and create a derived text artifact |
| `list_streams` | List active and recent live-stream sessions |
| `rotate_stream_key` | Generate or rotate the RTMP stream key for a stream source artifact |
| `get_stream_sessions` | List active sessions for a given stream source artifact |

Declared placeholders:

| Tool | Description |
|---|---|
| `validate_input` | Validate incoming content against rules or schemas |
| `normalize_artifact` | Normalize artifact content and encoding |
| `deduplicate` | Detect duplicate or near-duplicate artifacts |
| `classify_content` | Classify content by type, topic, or category |
| `connect_source` | Register an external connector for ingestion |
| `sync_source` | Pull latest content from a registered connector |
| `index_artifact` | Force explicit re-indexing of an artifact |
| `collect_telemetry` | Record system activity telemetry as artifacts |

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGIENCE_API_URI` | Yes | — | Base URI of the agience-core backend |
| `AGIENCE_API_KEY` | Yes | — | Platform API key (Bearer token) |
| `SRS_HTTP_API` | — | `http://localhost:1985` | SRS HTTP API base URL (for stream tools) |
| `STREAM_INGEST_URL` | — | `rtmp://localhost:1936/live` | Public RTMP ingest URL shown to OBS clients |
| `MCP_TRANSPORT` | — | `streamable-http` | MCP transport mode |
| `MCP_HOST` | — | `0.0.0.0` | Bind host |
| `MCP_PORT` | — | `8087` | HTTP port for MCP server |
| `LOG_LEVEL` | — | `INFO` | Logging level |

## Running

```bash
pip install -r requirements.txt
python server.py
```

For stream-side components, see `stream/README.md`.
