"""Parse MCP server artifacts into MCPServerConfig objects.

This module owns the knowledge of how ``vnd.agience.mcp-server+json`` context
is structured.  Core services call :func:`parse_mcp_server_artifact` without
needing to know the internal schema.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Optional

from mcp_client.contracts import MCPAuthConfig, MCPServerConfig, MCPServerTransport
from mcp_client.security import SSRFError, validate_url, validate_stdio_transport

logger = logging.getLogger(__name__)


def parse_mcp_server_artifact(artifact, *, allow_stdio: bool = False) -> Optional[MCPServerConfig]:
    """Parse a workspace artifact whose context describes an MCP server config.

    Expected context JSON shape::

        {
          "content_type": "application/vnd.agience.mcp-server+json",
          "title": "My Server",
          "transport": {
            "type": "http",              # "http" | "stdio"
            "well_known": "https://...", # for http
            "command": "npx",            # for stdio
            "args": [...],
            "env": { "API_KEY": "..." }
          },
          "notes": "optional description"
        }

    The artifact ``id`` is used as the server ID.
    """
    try:
        ctx: Dict = json.loads(artifact.context) if isinstance(artifact.context, str) else (artifact.context or {})
    except Exception:
        return None

    transport_raw = ctx.get("transport")
    if not isinstance(transport_raw, dict):
        return None

    transport_type = (transport_raw.get("type") or "").lower()
    if transport_type not in ("http", "stdio"):
        return None

    # Security validation
    if transport_type == "stdio":
        try:
            validate_stdio_transport(
                transport_raw.get("command", ""),
                allow_stdio=allow_stdio,
            )
        except ValueError as e:
            logger.warning("Rejected stdio transport for artifact %s: %s", artifact.id, e)
            return None

    if transport_type == "http":
        well_known = transport_raw.get("well_known")
        if well_known:
            try:
                validate_url(well_known)
            except (SSRFError, ValueError) as e:
                logger.warning("Rejected HTTP transport URL for artifact %s: %s", artifact.id, e)
                return None

    # Parse optional auth block
    auth_config = None
    auth_raw = ctx.get("auth")
    if isinstance(auth_raw, dict):
        auth_type = (auth_raw.get("type") or "none").lower()
        if auth_type in ("oauth2", "api_key", "static"):
            auth_config = MCPAuthConfig(
                type=auth_type,
                authorizer_id=auth_raw.get("authorizer_id"),
                secret_id=auth_raw.get("secret_id"),
                header=auth_raw.get("header"),
                value=auth_raw.get("value"),
            )

    try:
        transport = MCPServerTransport(**transport_raw)
        return MCPServerConfig(
            id=artifact.id,
            label=ctx.get("title") or ctx.get("label") or artifact.id,
            transport=transport,
            notes=ctx.get("notes"),
            auth=auth_config,
        )
    except Exception as e:
        logger.warning("Failed to parse MCP server artifact %s: %s", artifact.id, e)
        return None
