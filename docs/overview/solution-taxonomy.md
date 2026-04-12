# Agience Solution Codenames (End-State Taxonomy)

Status: **Reference**
Date: 2026-04-01

This taxonomy is public architecture vocabulary. It explains the product roles Agience is organized around.

## Eight codenames

| Codename | Domain | One-liner |
|---|---|---|
| **Astra** | Ingestion, Validation & Indexing | Capture and prepare incoming information |
| **Sage** | Research & Retrieval | Discover sources, gather evidence, rank relevance |
| **Verso** | Reasoning & Orchestration | Synthesize, coordinate multi-step tasks, evaluate |
| **Aria** | Presentation & Interface | Format, visualize, narrate — last mile to humans |
| **Nexus** | Networking, Transport & Routing | Connect agents, services, and external systems |
| **Seraph** | Security, Governance & Trust | Access control, audit, identity, policy compliance |
| **Atlas** | Provenance, Attribution & Lineage | Version lineage, conflict detection, traceability |
| **Ophan** | Finance, Economic Logic & Performance | Accounting, trade, resource allocation, budgeting, metrics |

## Pipeline position

```
Input:        Astra  — ingest, validate, normalize, index
Retrieval:    Sage   — search, retrieve, gather evidence
Reasoning:    Verso  — synthesize, reason, run operators
Output:       Aria   — format, visualize, present to humans

Cross-cutting:
  Nexus   — networking, messaging, routing, remote execution
  Seraph  — security, identity, access control, policy
  Atlas   — provenance, lineage, attribution, coherence
  Ophan   — finance, accounting, budgets, performance metrics
```

## Core codenames

### Astra — ingestion, validation & indexing
Primary responsibilities:
- Capture incoming information (files, URLs, streams, connectors)
- Validate and normalize content before it enters the workspace
- Deduplicate, classify, and index artifacts for retrieval
- Register external connectors as Agience-side artifact records (data pull routes through the official vendor MCP server)
- Telemetry collection from system inputs and activity streams

Typical MCP/tool surfaces:
- `ingest_file` — create workspace artifacts from file URLs or raw text
- `validate_input`, `normalize_artifact`, `deduplicate`, `classify_content`
- `connect_source`, `sync_source` — connector artifact registration + sync (official-first)
- `list_streams`, `transcribe` — live streaming integration
- `collect_telemetry`


---

### Sage — research & retrieval
Primary responsibilities:
- Hybrid search across workspaces and collections (BM25 + semantic kNN)
- Evidence-backed synthesis from retrieved sources
- External retrieval connectors (Azure AI Search)
- Research operations that produce reviewable outputs with provenance
- Meeting/transcript insights

Typical MCP/tool surfaces:
- `search`, `get_artifact`, `browse_collections`
- `search_azure`, `index_to_azure` — optional Azure AI Search connector
- `research`, `cite_sources` — multi-step retrieval + LLM synthesis (future)
- `ask`, `extract_information`, `generate_meeting_insights`


---

### Verso — reasoning & orchestration
Primary responsibilities:
- Synthesize information from multiple sources via LLM
- Execute defined multi-step operators
- Chain tool calls sequentially across agents
- Schedule deferred actions
- Evaluate output quality and submit training feedback

Typical MCP/tool surfaces:
- `synthesize` — LLM synthesis with artifact context
- `run_operator`, `chain_tasks`, `schedule_action`
- `evaluate_output`, `submit_feedback`

Artifact types owned:
- `application/vnd.agience.evaluation+json` — evaluation result


---

### Aria — presentation & interface
Primary responsibilities:
- Format content for human consumption (markdown, HTML, plain text)
- Render visualizations (charts, diagrams, tables)
- Adapt tone and language for target audiences
- Present workspace artifacts with appropriate layout
- Generate natural-language narratives from structured data

Typical MCP/tool surfaces:
- `format_response`, `present_artifact`
- `render_visualization`, `adapt_tone`, `narrate`


---

### Nexus — networking, transport & routing
Primary responsibilities:
- Platform-native messaging via channel adapters (Telegram, Slack, email)
- Webhook ingestion from external systems
- Service endpoint registration and routing
- Shell execution in sandboxed environments
- Secure tunnels from local host to platform
- Proxy tool calls to registered external MCP servers (official-first)

Typical MCP/tool surfaces:
- `send_message`, `get_messages`, `list_channels`
- `create_webhook`, `health_check`, `list_connections`
- `register_endpoint`, `route_request`
- `exec_shell`, `tunnel`, `proxy_tool`


---

### Seraph — security, governance & trust
Primary responsibilities:
- Access control (grant/revoke collection access)
- Audit trails (who accessed what, when)
- Identity verification (JWT/API key claims)
- API key lifecycle (rotation, scoping)
- Cryptographic signing of artifacts
- Policy enforcement and compliance checking

Typical MCP/tool surfaces:
- `audit_access`, `list_audit_events`
- `check_permissions`, `grant_access`, `revoke_access`
- `rotate_api_key`, `verify_token`
- `sign_artifact`, `enforce_policy`, `list_policies`, `check_compliance`


---

### Atlas — provenance, attribution & lineage
Primary responsibilities:
- Trace artifact version lineage and source attribution
- Detect conflicting claims across workspace or collection
- Validate workspaces against contract artifacts
- Propose merges of divergent artifact versions
- Graph traversal across knowledge relationships
- Human-in-the-loop approval gates

Typical MCP/tool surfaces:
- `check_provenance`, `attribute_source`
- `detect_conflicts`, `check_coherence`
- `apply_contract`, `suggest_merge`
- `traverse_graph`


---

### Ophan — finance, economic logic & performance
Primary responsibilities:
- Value transfers (crypto on-chain, fiat bank/wire)
- Double-entry ledger recording and reconciliation
- Invoice creation and payment application
- Market data (price feeds, OHLCV, portfolio)
- Resource usage tracking and budget calculation
- System performance and efficiency metrics

Credentials model: BYOK — exchange/bank keys stored as encrypted user secrets, retrieved per-request from `/secrets`. Never in server env vars.

Typical MCP/tool surfaces:
- `send_payment`, `record_transaction`, `get_transaction`, `list_transactions`
- `fetch_statement`, `get_balance`, `reconcile_account`
- `create_invoice`, `apply_payment`, `run_report`
- `get_price`, `get_market_data`, `track_wallet`, `get_portfolio`, `calculate_pnl`
- `track_resource_usage`, `get_metrics`, `calculate_budget`


---

## Pillar mapping

| Pillar | Primary codename | Notes |
|---|---|---|
| Ingestion & Indexing | Astra | Capture, validate, normalize, index |
| Research & Retrieval | Sage | Hybrid search, evidence synthesis, meeting insights |
| Reasoning & Orchestration | Verso | Synthesis, multi-step operators, evaluation |
| Presentation & Interface | Aria | Format, visualize, narrate to humans |
| Networking & Infrastructure | Nexus | Messaging, routing, tunnels, proxy |
| Security & Governance | Seraph | Access control, audit, identity, policy |
| Provenance & Lineage | Atlas | Attribution, conflict detection, contracts |
| Finance & Performance | Ophan | Accounting, trade, metrics, budgets |

## Notes
- **Running operators** and recording **receipts/provenance** are core Agience framework capabilities (not a separate pillar).
- **Official-first**: Agience never duplicates what an official vendor MCP server provides. External servers (GitHub, AWS, filesystem, Slack, etc.) are registered as `vnd.agience.mcp-server+json` artifacts. Nexus's `proxy_tool` and Astra's `connect_source`/`sync_source` are the integration points — they route through official servers, not around them.
