"""MCP resource / capability importer.

Operation-dispatcher native targets for the `vnd.agience.mcp-server+json`
type's `resources_read`, `resources_import`, and `materialize_capabilities`
operations.

Replaces the corresponding `dispatch_resources_*` functions in the old
`mcp_service.py`. The transport layer (calling out to the MCP server) is
now `chorus_client` — mantle no longer holds an in-process MCP client.
The artifact-creation logic stays here in mantle because it walks the
local Arango (sub-collections, deterministic UUIDs, archive-stale).

JSON-RPC item shapes consumed (from chorus's gateway forwarding to the
target persona's FastMCP handlers):

  tool:     {"name": str, "description": str, "inputSchema": dict}
  resource: {"uri": str, "name": str, "description": str, "mimeType": str}
  prompt:   {"name": str, "description": str, "arguments": list}

These are JSON-RPC (`tools/list` / `resources/list` / `prompts/list`)
payload shapes — plain dicts. We don't depend on any dataclass wrapper.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from arango.database import StandardDatabase

from db import arango as arango_db_module
from db.arango import (
    add_artifact_to_collection as db_add_artifact_to_collection,
    create_artifact as db_create_artifact,
    get_artifact as db_get_artifact,
    list_collection_artifacts as _db_list_collection_artifacts,
    update_artifact as db_update_artifact,
)
from entities.artifact import Artifact as ArtifactEntity
from entities.collection import COLLECTION_CONTENT_TYPE

from services import chorus_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Content types
# ---------------------------------------------------------------------------

_TOOL_CONTENT_TYPE = "application/vnd.agience.tool+json"
_RESOURCE_CONTENT_TYPE = "application/vnd.agience.resource+json"
_PROMPT_CONTENT_TYPE = "application/vnd.agience.prompt+json"

_KIND_MAP = {
    "tool": _TOOL_CONTENT_TYPE,
    "resource": _RESOURCE_CONTENT_TYPE,
    "prompt": _PROMPT_CONTENT_TYPE,
}


# ---------------------------------------------------------------------------
# Capability artifact builders (plain JSON-RPC dict in → context dict out)
# ---------------------------------------------------------------------------


def _deterministic_id(server_root_id: str, kind: str, name: str) -> str:
    """Compute a deterministic UUID5 for a capability artifact."""
    return str(uuid.uuid5(uuid.UUID(server_root_id), f"{kind}:{name}"))


def _build_tool_context(tool: Dict[str, Any]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "content_type": _TOOL_CONTENT_TYPE,
        "tool_name": tool.get("name", ""),
    }
    if tool.get("description"):
        ctx["description"] = tool["description"]
    if tool.get("inputSchema"):
        ctx["input_schema"] = tool["inputSchema"]
    return ctx


def _build_resource_context(resource: Dict[str, Any]) -> Dict[str, Any]:
    uri = resource.get("uri") or resource.get("name") or ""
    ctx: Dict[str, Any] = {
        "content_type": _RESOURCE_CONTENT_TYPE,
        "uri": uri,
    }
    if resource.get("mimeType"):
        ctx["mime_type"] = resource["mimeType"]
    if resource.get("description") or resource.get("name"):
        ctx["description"] = resource.get("description") or resource.get("name")
    return ctx


def _build_prompt_context(prompt: Dict[str, Any]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "content_type": _PROMPT_CONTENT_TYPE,
        "prompt_name": prompt.get("name", ""),
    }
    if prompt.get("description"):
        ctx["description"] = prompt["description"]
    if prompt.get("arguments"):
        ctx["arguments"] = prompt["arguments"]
    return ctx


def _capability_name(kind: str, item: Dict[str, Any]) -> str:
    if kind == "resource":
        return str(item.get("uri") or item.get("name") or "")
    return str(item.get("name") or "")


# ---------------------------------------------------------------------------
# Sub-collection + artifact upsert helpers
# ---------------------------------------------------------------------------


def _upsert_capability_artifact(
    db: StandardDatabase,
    *,
    artifact_id: str,
    collection_id: str,
    content_type: str,
    context: Dict[str, Any],
    content: str,
    user_id: str,
) -> bool:
    """Create or update a capability artifact. Returns True if created/updated."""
    now = datetime.now(timezone.utc).isoformat()
    context_str = json.dumps(context, separators=(",", ":"), ensure_ascii=False)
    existing = db_get_artifact(db, artifact_id)

    if existing is not None:
        if existing.context == context_str and existing.state != ArtifactEntity.STATE_ARCHIVED:
            return False
        existing.context = context_str
        existing.content = content
        existing.state = ArtifactEntity.STATE_COMMITTED
        existing.modified_by = user_id
        existing.modified_time = now
        db_update_artifact(db, existing)
        return True

    artifact = ArtifactEntity(
        id=artifact_id,
        root_id=artifact_id,
        collection_id=collection_id,
        state=ArtifactEntity.STATE_COMMITTED,
        context=context_str,
        content=content,
        content_type=content_type,
        created_by=user_id,
        created_time=now,
    )
    db_create_artifact(db, artifact)
    db_add_artifact_to_collection(
        db, collection_id, artifact_id,
        origin=True, propagate=["read", "invoke"],
    )
    return True


def _ensure_subcollection(
    db: StandardDatabase,
    server_root_id: str,
    kind: str,
    label: str,
    user_id: str,
) -> str:
    """Ensure a sub-collection artifact exists for a capability kind."""
    col_id = _deterministic_id(server_root_id, "collection", kind)
    existing = db_get_artifact(db, col_id)
    if existing is not None:
        return col_id

    now = datetime.now(timezone.utc).isoformat()
    col_artifact = ArtifactEntity(
        id=col_id,
        root_id=col_id,
        collection_id=server_root_id,
        state=ArtifactEntity.STATE_COMMITTED,
        context=json.dumps({"content_type": COLLECTION_CONTENT_TYPE}, separators=(",", ":")),
        content="",
        content_type=COLLECTION_CONTENT_TYPE,
        name=label,
        created_by=user_id,
        created_time=now,
    )
    db_create_artifact(db, col_artifact)
    db_add_artifact_to_collection(
        db, server_root_id, col_id,
        origin=True, propagate=["read", "invoke"],
    )
    return col_id


def _archive_stale_capabilities(
    db: StandardDatabase,
    parent_id: str,
    live_ids: Set[str],
    user_id: str,
) -> int:
    count = 0
    for art_dict in _db_list_collection_artifacts(db, parent_id):
        art_id = art_dict.get("id") or art_dict.get("_key")
        if not art_id or art_id in live_ids:
            continue
        art = ArtifactEntity.from_dict(art_dict)
        if art.state == ArtifactEntity.STATE_ARCHIVED:
            continue
        art.state = ArtifactEntity.STATE_ARCHIVED
        art.modified_by = user_id
        art.modified_time = datetime.now(timezone.utc).isoformat()
        db_update_artifact(db, art)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def import_resources_as_artifacts(
    db: StandardDatabase,
    user_id: str,
    workspace_id: str,
    server_artifact_id: str,
    resources: List[Dict[str, Any]],
) -> List[str]:
    """Create workspace artifacts for selected MCP resources.

    `server_artifact_id` is the seeded MCP-server artifact UUID.
    Returns the list of created artifact IDs.
    """
    ws_grants = arango_db_module.get_active_grants_for_principal_resource(
        db, grantee_id=user_id, resource_id=workspace_id,
    )
    if not any(getattr(g, "can_create", False) for g in ws_grants):
        raise ValueError("Workspace not found")

    from services.workspace_service import create_workspace_artifacts_bulk

    items: List[Dict[str, Any]] = []
    for r in resources or []:
        kind = r.get("kind") or "text"
        uri = r.get("uri")
        text = r.get("text") or ""
        title = r.get("title") or uri or kind

        ctx = {
            "content_type": "application/vnd.agience.resource+json",
            "content_source": "mcp-resource",
            "server": server_artifact_id,
            "kind": kind,
            "uri": uri,
            "title": title,
            "props": r.get("props") or {},
        }
        content = text if isinstance(text, str) else json.dumps(text)
        items.append({"context": json.dumps(ctx), "content": content})

    created = create_workspace_artifacts_bulk(db, user_id, workspace_id, items)
    return [a.id for a in created if a.id]


def materialize_server_capabilities(
    db: StandardDatabase,
    server_root_id: str,
    user_id: str,
) -> Dict[str, int]:
    """Materialize MCP server capabilities as child artifacts.

    Calls `tools/list`, `resources/list`, `prompts/list` via chorus's
    universal gateway, then creates / updates artifacts for each
    capability. Idempotent — safe to call repeatedly.

    Returns counts: ``{"tools": N, "resources": N, "prompts": N}``.
    """
    caps = chorus_client.list_capabilities(server_root_id, user_id=user_id)

    tools_count = _materialize_kind(
        db, server_root_id, "tool", caps.get("tools") or [],
        _build_tool_context, user_id,
    )
    resources_count = _materialize_kind(
        db, server_root_id, "resource", caps.get("resources") or [],
        _build_resource_context, user_id,
    )
    prompts_count = _materialize_kind(
        db, server_root_id, "prompt", caps.get("prompts") or [],
        _build_prompt_context, user_id,
    )

    logger.info(
        "Materialized capabilities for server %s: %d tools, %d resources, %d prompts",
        server_root_id, tools_count, resources_count, prompts_count,
    )
    return {"tools": tools_count, "resources": resources_count, "prompts": prompts_count}


def _materialize_kind(
    db: StandardDatabase,
    server_root_id: str,
    kind: str,
    items: List[Dict[str, Any]],
    build_context,
    user_id: str,
) -> int:
    if not items:
        return 0

    label_map = {"tool": "Tools", "resource": "Resources", "prompt": "Prompts"}
    subcol_id = _ensure_subcollection(
        db, server_root_id, kind, label_map.get(kind, kind.title()), user_id,
    )
    content_type = _KIND_MAP[kind]
    live_ids: Set[str] = set()

    for item in items:
        name = _capability_name(kind, item)
        if not name:
            continue
        art_id = _deterministic_id(server_root_id, kind, name)
        live_ids.add(art_id)
        ctx = build_context(item)
        content = ctx.get("description", name)

        _upsert_capability_artifact(
            db,
            artifact_id=art_id,
            collection_id=subcol_id,
            content_type=content_type,
            context=ctx,
            content=content,
            user_id=user_id,
        )
        db_add_artifact_to_collection(
            db, subcol_id, art_id,
            origin=True, propagate=["read", "invoke"],
        )

    _archive_stale_capabilities(db, subcol_id, live_ids, user_id)
    return len(items)


# ---------------------------------------------------------------------------
# Operation-dispatcher native targets
#
# Wired by Iris's `vnd.agience.mcp-server+json` type.json `dispatch.target`
# strings:
#
#   operations.resources_read           → mcp_resource_importer.dispatch_resources_read
#   operations.resources_import         → mcp_resource_importer.dispatch_resources_import
#   operations.materialize_capabilities → mcp_resource_importer.dispatch_materialize_capabilities
# ---------------------------------------------------------------------------


def dispatch_resources_read(artifact: Dict, body: Dict, ctx) -> Dict:
    """Read an MCP resource by URI from the server represented by *artifact*.

    Returns the first content item from the MCP ReadResourceResult flattened
    to the MCPResourceContents shape the frontend expects:
        { uri, mimeType?, text? }   for text resources
        { uri, mimeType?, blob? }   for blob resources
    """
    if not isinstance(body, dict):
        raise ValueError("resources_read requires a JSON object body")

    uri = body.get("uri")
    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("resources_read requires body.uri (string)")

    server_artifact_id = artifact.get("root_id") or artifact.get("_key") or artifact.get("id")
    if not server_artifact_id:
        raise ValueError("Cannot resolve server artifact id from dispatch target")

    result = chorus_client.read_resource(
        str(server_artifact_id),
        uri.strip(),
        user_id=ctx.user_id,
    )

    # chorus_client returns {"contents": [TextResourceContents | BlobResourceContents]}
    # The frontend MCPResourceContents interface is flat (uri, mimeType, text, blob).
    contents = result.get("contents") if isinstance(result, dict) else None
    if not contents or not isinstance(contents, list):
        raise ValueError(f"No content returned for resource '{uri}'")

    return contents[0]


def dispatch_resources_import(artifact: Dict, body: Dict, ctx) -> Dict:
    """Materialize a list of MCP resources as workspace artifacts."""
    if not isinstance(body, dict):
        raise ValueError("resources_import requires a JSON object body")

    workspace_id = body.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError("resources_import requires body.workspace_id (string)")

    resources = body.get("resources")
    if not isinstance(resources, list):
        raise ValueError("resources_import requires body.resources (array)")

    server_artifact_id = artifact.get("root_id") or artifact.get("_key") or artifact.get("id")
    if not server_artifact_id:
        raise ValueError("Cannot resolve server artifact id from dispatch target")

    created_ids = import_resources_as_artifacts(
        db=ctx.arango_db,
        user_id=ctx.user_id,
        workspace_id=workspace_id.strip(),
        server_artifact_id=str(server_artifact_id),
        resources=resources,
    )
    return {"created_artifact_ids": created_ids, "count": len(created_ids)}


def dispatch_materialize_capabilities(artifact: Dict, body: Dict, ctx) -> Dict:
    """Connect to the MCP server and materialize tools/resources/prompts."""
    server_artifact_id = artifact.get("root_id") or artifact.get("_key") or artifact.get("id")
    if not server_artifact_id:
        raise ValueError("Cannot resolve server artifact id from dispatch target")

    return materialize_server_capabilities(
        db=ctx.arango_db,
        server_root_id=str(server_artifact_id),
        user_id=ctx.user_id,
    )

