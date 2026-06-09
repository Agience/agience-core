"""Outbound MCP-tool calls from mantle to chorus.

Replaces the in-process `mcp_service.invoke_tool` path. Mantle publishes no
MCP surface itself; tool dispatch goes over the network to Chorus's
universal gateway, which routes by the `vnd.agience.mcp-server+json`
artifact's `kind` (persona / external / relay).

Auth: the user identity flows in an RFC-8693 delegation JWT signed with
mantle's service identity (`audience=chorus`, `sub=user_id`). Chorus's
gateway verifies, then forwards into the persona's MCP middleware (which
re-verifies against the authority manifest).

This module is the only mechanism mantle-side code uses to invoke a
remote MCP tool. The previous `services/mcp_service.invoke_tool` path
went away with Step F of the consolidation.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from kernel import config, service_identity

logger = logging.getLogger(__name__)


_TIMEOUT_S = 30.0

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def is_uuid_like(value: str) -> bool:
    """Cheap shape check; avoids a registry lookup for clearly-UUID server ids."""
    return bool(_UUID_RE.match(value or ""))


def _auth_headers(user_id: str) -> dict[str, str]:
    """Build the delegation JWT Authorization header for a Chorus call."""
    delegation = service_identity.sign_delegation_jwt(
        audience="chorus",
        user_sub=user_id,
    )
    return {"Authorization": f"Bearer {delegation}"}


def _mcp_url(server_artifact_id: str) -> str:
    return f"{config.CHORUS_URI.rstrip('/')}/{server_artifact_id}/mcp"


def call_tool(
    server_artifact_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    user_id: str,
) -> Any:
    """Invoke an MCP tool on a server through Chorus's universal gateway.

    `server_artifact_id` is the UUID of the `vnd.agience.mcp-server+json`
    artifact. Callers are responsible for resolving short persona names
    (e.g. `"verso"`) via `services.server_registry.resolve_name_to_id`
    before calling — this helper does no name resolution.

    Returns the tool result content list on success.
    """
    async def _do() -> Any:
        async with streamablehttp_client(
            _mcp_url(server_artifact_id),
            headers=_auth_headers(user_id),
            timeout=_TIMEOUT_S,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments or {})
                if result.isError:
                    raise RuntimeError(
                        f"MCP tool '{tool_name}' returned an error: {result.content}"
                    )
                return [c.model_dump() for c in result.content]

    return asyncio.run(_do())


def read_resource(
    server_artifact_id: str,
    uri: str,
    *,
    user_id: str,
) -> Dict[str, Any]:
    """Read an MCP resource by URI through Chorus's gateway.

    Returns `{"contents": [...]}` where each entry is the serialised
    resource content item (text or blob).
    """
    async def _do() -> Dict[str, Any]:
        async with streamablehttp_client(
            _mcp_url(server_artifact_id),
            headers=_auth_headers(user_id),
            timeout=_TIMEOUT_S,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.read_resource(uri)  # type: ignore[arg-type]
                return {"contents": [c.model_dump() for c in result.contents]}

    return asyncio.run(_do())


def list_capabilities(
    server_artifact_id: str,
    *,
    user_id: str,
) -> Dict[str, list]:
    """List a server's tools, resources, and prompts in a single MCP session.

    Returns:
        {"tools": [...], "resources": [...], "prompts": [...]}

    Each entry is the serialised MCP item shape. Failures on any individual
    list are logged and produce an empty list — partial capability data is
    preferable to no data at all.
    """
    async def _do() -> Dict[str, list]:
        out: Dict[str, list] = {"tools": [], "resources": [], "prompts": []}
        async with streamablehttp_client(
            _mcp_url(server_artifact_id),
            headers=_auth_headers(user_id),
            timeout=_TIMEOUT_S,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                for kind, fetch in (
                    ("tools",     session.list_tools),
                    ("resources", session.list_resources),
                    ("prompts",   session.list_prompts),
                ):
                    try:
                        result = await fetch()
                        items = getattr(result, kind, []) or []
                        out[kind] = [i.model_dump() for i in items]
                    except Exception as exc:
                        logger.warning(
                            "list_capabilities: %s failed for server %s: %s",
                            kind, server_artifact_id, exc,
                        )
        return out

    return asyncio.run(_do())
