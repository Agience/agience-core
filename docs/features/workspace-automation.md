# Workspace Automation

Status: **Reference**
Date: 2026-04-01

Workspace automation enables declarative, event-driven workflows within Agience. Instead of imperative "detect and respond" code, automations are pre-configured rules that trigger actions when specific workspace events occur.

**Core idea:** The workspace is the context boundary. Each workspace defines what events it receives (via MCP server attachments), what knowledge it has access to (via collection attachments), and what to do when events occur (via automation rules).

---

## Overview

### Workspace as orchestration context

```
┌─────────────────────────────────────────┐
│          Workspace: "Support"           │
├─────────────────────────────────────────┤
│ MCP Attachments:                        │
│  - mcp-telegram (customer messages)     │
│  - mcp-slack (internal notifications)   │
│                                         │
│ Collection Attachments:                 │
│  - Support FAQ                          │
│  - Product Documentation                │
│  - Customer History                     │
│                                         │
│ Automations:                            │
│  ┌────────────────────────────────────┐ │
│  │ Trigger: on_message_received       │ │
│  │   Platform: telegram               │ │
│  │ Action: invoke_operator            │ │
│  │   Operator: local.support_triage   │ │
│  │   Instructions: "Categorize..."    │ │
│  │ Then: call_mcp_tool                │ │
│  │   Tool: mcp.telegram.send_message  │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

---

## Workspace event handlers

Workspace event handlers are **workspace artifacts** that define event-driven automations. They are data, not code — they live in the workspace like any other artifact and can be edited, copied, and committed to collections.

An artifact is treated as an event handler when its `context.type` is `"workspace-event-handler"`.

### Handler artifact schema

```json
{
  "type": "workspace-event-handler",
  "title": "Auto-chunk uploads",
  "enabled": true,
  "on": {
    "event_types": ["upload_complete"],
    "source": {
      "context_type": "optional-context.type-match",
      "mime": "optional-mime-match",
      "require_transcript_status": "optional-status-match"
    }
  },
  "actions": [
    {
      "type": "invoke_operator",
      "operator": "ingest_runner",
      "operator_params": {
        "create_chunks": true,
        "create_units": false
      }
    }
  ]
}
```

### Event types

Common workspace events:

| Event | Description |
|---|---|
| `artifact_created` | A new artifact was created in the workspace |
| `artifact_updated` | An artifact was modified |
| `artifact_deleted` | An artifact was deleted |
| `upload_complete` | A file upload finished processing |

The dispatch payload includes `workspace_id`, `event_type`, and the affected `artifact_id`. Handlers are not triggered by events where the source artifact is itself a handler.

### Actions

#### `invoke_operator`

Invokes an operator by ID.

**Parameters automatically injected:**
- `workspace_id`
- `source_artifact_id` and `artifact_id` (both set to the triggering artifact ID)

**Template variables** in `operator_params` strings:
- `{{workspace_id}}`, `{{event_type}}`, `{{artifact_id}}`, `{{origin}}`, `{{stream}}`

---

## Automation schema

Automations stored in `workspace.extensions.automations[]` define more complex, multi-step event-driven workflows.

```json
{
  "id": "auto_123",
  "name": "Respond to customer messages",
  "enabled": true,
  "trigger": {
    "type": "on_message_received",
    "conditions": {
      "platform": "telegram",
      "sender_type": "customer"
    }
  },
  "actions": [
    {
      "type": "invoke_operator",
      "operator": "local.support_triage",
      "instructions": "Analyze customer message and determine urgency",
      "input_from": "trigger.artifact",
      "context_artifacts": "thread_history"
    },
    {
      "type": "conditional",
      "condition": "agent_response.metadata.urgency == 'high'",
      "then": [
        {
          "type": "call_mcp_tool",
          "server_id": "telegram",
          "tool": "send_message",
          "arguments": {
            "chat_id": "trigger.artifact.context.sender_id",
            "text": "agent_response.output"
          }
        }
      ],
      "else": [
        {
          "type": "create_artifact",
          "title": "Queued support request",
          "state": "draft"
        }
      ]
    }
  ]
}
```

---

## Trigger types

### `on_message_received`

Fires when an external message arrives via MCP server.

Trigger artifact context includes: `content_source: "message-inbound"`, `platform`, `sender_id`, `sender_name`, `thread_id`, `timestamp`

Conditions: `platform`, `sender_type` (customer | internal | bot), `content_pattern` (regex), `sender_id`

### `on_artifact_created`

Fires when a new artifact is created in the workspace.

Conditions: `content_source`, `has_tag`, `mime_type`

### `on_artifact_modified`

Fires when an artifact is updated.

Conditions: `state_changed_to` (draft, committed, archived), `field_changed` (title, description, content, context)

### `on_time`

Scheduled / cron-based trigger.

Config: `schedule` (cron expression, e.g., `0 9 * * *`), `timezone`

### `on_commit`

Fires when artifacts are committed to a collection.

Conditions: `collection_id`, `artifact_count` (minimum threshold)

---

## Action types

### `invoke_operator`

Calls an operator with workspace context.

| Parameter | Description |
|---|---|
| `operator` | Operator name (for example `ingest_runner`) |
| `instructions` | Task-specific prompt |
| `input_from` | Source of agent input: `trigger.artifact`, `selected_artifacts`, or `literal` |
| `context_artifacts` | Additional context: `thread_history`, `collection:FAQ`, `all` |
| `operator_params` | Operator-specific parameters |

### `call_mcp_tool`

Direct MCP tool invocation.

| Parameter | Description |
|---|---|
| `server_id` | MCP server from workspace attachments |
| `tool` | Tool name |
| `arguments` | Tool arguments — supports variable interpolation |

**Variable interpolation:**
- `trigger.artifact.context.sender_id` — value from triggering artifact
- `agent_response.output` — last agent action result
- `workspace.variable.<name>` — workspace-level variables

### `create_artifact`

Creates a new artifact in the workspace.

| Parameter | Description |
|---|---|
| `title`, `description`, `content` | Artifact fields |
| `state` | Initial state (typically `draft`) |
| `context` | Additional metadata |
| `parent_id` | Link to an existing artifact for threading |

### `update_artifact`

Modifies an existing artifact.

| Parameter | Description |
|---|---|
| `artifact_id` | Target (can be `trigger.artifact.id`) |
| `fields` | Fields to update |
| `append_content` | Add to existing content |

### `conditional`

Branches based on an expression.

```json
{
  "type": "conditional",
  "condition": "agent_response.metadata.urgency == 'high'",
  "then": [...],
  "else": [...]
}
```

Expression examples:
- `agent_response.metadata.priority == 'urgent'`
- `trigger.artifact.content contains 'urgent'`
- `current_time.hour >= 9 and current_time.hour < 17`

### `send_notification`

Sends an internal Agience notification.

| Parameter | Description |
|---|---|
| `recipient` | User ID or role |
| `title`, `message` | Notification content |
| `link_to_card` | Artifact to highlight |

### `route_to_workspace`

Moves or copies an artifact to another workspace.

| Parameter | Description |
|---|---|
| `workspace_id` | Target workspace |
| `mode` | `move` or `copy` |
| `trigger_automations` | Run target workspace automations |

---

## Example automations

### Customer support bot

```json
{
  "trigger": {"type": "on_message_received", "conditions": {"platform": "telegram"}},
  "actions": [
    {
      "type": "invoke_operator",
      "operator": "llm.gpt-4o-mini",
      "instructions": "You are a customer support agent. Answer using FAQ and product docs.",
      "context_artifacts": "collection:FAQ,collection:ProductDocs,thread_history"
    },
    {
      "type": "call_mcp_tool",
      "server_id": "telegram",
      "tool": "send_message",
      "arguments": {
        "chat_id": "trigger.artifact.context.sender_id",
        "text": "agent_response.output"
      }
    }
  ]
}
```

### Daily digest

```json
{
  "trigger": {"type": "on_time", "schedule": "0 9 * * *"},
  "actions": [
    {
      "type": "invoke_operator",
      "operator": "local.daily_digest",
      "input_from": "literal",
      "params": {"since": "24h"}
    },
    {
      "type": "call_mcp_tool",
      "server_id": "email",
      "tool": "send_email",
      "arguments": {
        "to": "user@example.com",
        "subject": "Daily Digest",
        "body": "agent_response.output"
      }
    }
  ]
}
```

### Smart triage with routing

```json
{
  "trigger": {"type": "on_message_received"},
  "actions": [
    {
      "type": "invoke_operator",
      "operator": "local.triage_classifier",
      "instructions": "Categorize: urgent, normal, low priority"
    },
    {
      "type": "conditional",
      "condition": "agent_response.metadata.priority == 'urgent'",
      "then": [
        {"type": "call_mcp_tool", "server_id": "slack", "tool": "notify_channel", "arguments": {"channel": "#urgent-support"}},
        {"type": "route_to_workspace", "workspace_id": "ws_urgent"}
      ],
      "else": [
        {"type": "route_to_workspace", "workspace_id": "ws_queue"}
      ]
    }
  ]
}
```

---

## Security and governance

### Permission model

- Only the workspace owner can create or edit automations.
- Inbound integrations authenticate with grant tokens (JWT) and are authorized by grants.
- Automation execution runs with workspace owner privileges.
- Rate limiting is enforced per automation to prevent runaway loops.

### Audit trail

Every automation execution is logged with: trigger type and conditions, actions executed, agent invocations and responses, MCP tool calls and results, duration and resource usage.

### Safety controls

- Max execution time per automation (300s default)
- Max actions per execution (20 default)
- Loop detection (same automation cannot trigger itself)
- Quota limits (executions per hour/day)
