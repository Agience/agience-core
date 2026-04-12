# agience-server-sage

Status: **Reference** --- current server.py surface
Date: 2026-03-31

Sage is the research and retrieval persona. It exposes hybrid search, artifact lookup, collection browsing, and optional Azure AI Search projection.

## Current MCP Tools

Implemented paths:

| Tool | Description |
|---|---|
| `search` | Run hybrid search across workspaces and collections |
| `get_artifact` | Fetch a single artifact by ID |
| `browse_collections` | List committed collections visible to the caller |
| `search_azure` | Query an Azure AI Search index using a provided connection object |
| `index_to_azure` | Project workspace artifacts into an Azure AI Search index |

Declared placeholders:

| Tool | Description |
|---|---|
| `research` | Multi-step retrieval plus synthesis |
| `cite_sources` | Produce a provenance receipt for a synthesized answer |
| `ask` | Search plus synthesis in a single tool call |
| `extract_information` | Extract structured fields from artifact content |
| `generate_meeting_insights` | Derive summary, actions, and coaching from a transcript artifact |

## UI Resources

Sage currently serves `ui://Sage/vnd.agience.research.html` for the research artifact viewer.

## Azure Integration

`azure_search.py` provides the Azure adapter layer. Azure credentials are supplied via the connection object passed to the relevant tools; they are not loaded from fixed environment variables in `server.py`.

## Configuration

- `AGIENCE_API_URI`
- `AGIENCE_API_KEY`
- `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `LOG_LEVEL`

## Running

```bash
pip install -r requirements.txt
python server.py
```
