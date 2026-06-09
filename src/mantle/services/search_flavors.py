"""Native search flavors + flavor dispatch.

A ``vnd.agience.search+json`` artifact is an invokable *search flavor*. Its type
declares one operation, ``invoke``, dispatching to the native target
``run_search`` here. Mirroring Verso's Transform pattern, the artifact's
``context.run`` block selects the actual behavior:

    {"type": "standard"}                                  → open RRF search (in core)
    {"type": "mcp-tool", "server": "beacon",              → premium flavor in an
     "tool": "premium_search", "requires_feature": "beacon"}  external server

The **gate lives here, in core, keyed on the invoking user**: a flavor whose run
block names ``requires_feature`` is only dispatched when
``gate_service.has_feature(user, <feature>)``. Anchors/search stay open; only the
premium *flavor interaction* is gated. See `.dev/features/search-as-artifact.md`.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _run_block(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the artifact's ``context.run`` block (context may be a JSON string)."""
    ctx = artifact.get("context") or {}
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except json.JSONDecodeError:
            ctx = {}
    run = ctx.get("run") if isinstance(ctx, dict) else None
    return run if isinstance(run, dict) else {}


async def run_search(artifact: Dict[str, Any], body: Dict[str, Any], ctx: Any) -> Dict[str, Any]:
    """Native dispatch target for ``vnd.agience.search+json`` ``invoke``.

    Reads ``context.run`` to pick the flavor, enforces any ``requires_feature``
    entitlement against the invoking user, then runs the standard flavor in-core
    or proxies to a premium server tool.
    """
    run = _run_block(artifact)
    flavor = run.get("type", "standard")
    feature = run.get("requires_feature")

    if feature:
        from services import gate_service

        db = getattr(ctx, "arango_db", None)
        user_id = getattr(ctx, "user_id", None)
        if not (user_id and db is not None and gate_service.has_feature(db, user_id, feature)):
            raise HTTPException(
                status_code=403,
                detail=f"This search flavor requires the '{feature}' entitlement",
            )

    if flavor in ("standard", "native"):
        return await standard_search(artifact, body, ctx)

    if flavor == "mcp-tool":
        server = run.get("server")
        tool = run.get("tool")
        if not server or not tool:
            return {"error": "premium search run block missing 'server' or 'tool'"}

        from services import chorus_client, platform_topology, server_registry

        # chorus_client.call_tool needs the server artifact UUID, not a name/slug.
        # Resolve in order: namespace/slug (external add-ons like Beacon) → persona
        # manifest name → bare bootstrap UUID passthrough.
        server_id = None
        if "/" in server:
            server_id = platform_topology.get_id_optional(server)
        else:
            try:
                server_id = server_registry.resolve_name_to_id(server)
            except (ValueError, KeyError):
                server_id = server if ("-" in server and len(server) >= 32) else None
        if not server_id:
            raise HTTPException(
                status_code=503,
                detail=f"Search flavor server '{server}' is not registered/available",
            )

        user_id = getattr(ctx, "user_id", None)
        result = await chorus_client.call_tool(server_id, tool, dict(body or {}), user_id=user_id)
        return result if isinstance(result, dict) else {"result": result}

    return {"error": f"unknown search flavor run.type {flavor!r}"}


async def standard_search(artifact: Dict[str, Any], body: Dict[str, Any], ctx: Any) -> Dict[str, Any]:
    """Standard (open) search flavor — the canonical SSE + MANTLE RRF search.

    Runs for the invoking user (light-cone enforced inside the accessor) and
    returns ranked hits. Zero dependency on any premium add-on.
    """
    from search.types import SearchQuery
    from search.mantle.wiring import build_sse_search_accessor

    user_id = getattr(ctx, "user_id", None) or ""
    arango_db = getattr(ctx, "arango_db", None)
    if arango_db is None:
        raise ValueError("standard_search requires ctx.arango_db")

    body = body or {}
    query = SearchQuery(
        query_text=body.get("query_text") or body.get("query") or "",
        query_embedding=body.get("embedding"),
        user_id=user_id,
        scope=body.get("scope"),
        use_hybrid=body.get("use_hybrid"),
        aperture=0.75,
        from_=int(body.get("from", 0) or 0),
        size=int(body.get("size", 20) or 20),
        sort="relevance",
        highlight=False,
    )

    accessor = build_sse_search_accessor(arango_db)
    if accessor is None:
        return {"error": "encrypted search unavailable", "hits": [], "total": 0, "flavor": "standard"}

    result = accessor.search(query)
    return {
        "flavor": "standard",
        "total": result.total,
        "used_hybrid": result.used_hybrid,
        "hits": [
            {
                "id": h.doc_id,
                "score": h.score,
                "root_id": h.root_id,
                "collection_id": h.collection_id,
                "title": h.title or None,
            }
            for h in result.hits
        ],
    }
