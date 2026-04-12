"""MCP client-side router — live capability introspection only.

Phase 7D — Server Artifact Proxy: tool invocation, resource read, and
resource import are no longer dedicated router endpoints. They flow
through the unified artifact + operations surface:

- Tool invocation:  ``POST /artifacts/{server_id}/invoke``
                    body ``{name, arguments, workspace_id?}``
- Resource read:    ``POST /artifacts/{server_id}/op/resources_read``
                    body ``{uri, workspace_id?}``
- Resource import:  ``POST /artifacts/{server_id}/op/resources_import``
                    body ``{workspace_id, resources}``

The two endpoints that remain in this router are **live capability
introspection** — they connect to each accessible MCP server and return
the live tools/resources/prompts. This is a legitimate platform concern
that does not fit the artifact-CRUD model: the data is not stored, it is
fetched on demand from the running server.

- ``GET /mcp/servers``                       — live capabilities for all
  accessible MCP servers (built-in personas + collection-committed
  third-party servers + active desktop-host relays).
- ``GET /mcp/workspaces/{id}/servers``       — live capabilities scoped
  to a workspace (built-in personas + workspace-local mcp-server
  artifacts).

The persistent server artifact records are listed via the generic
``GET /artifacts?content_type=application/vnd.agience.mcp-server+json``
endpoint when only the registration metadata is needed.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status
from arango.database import StandardDatabase

from core.dependencies import get_arango_db
from services.dependencies import get_auth, AuthContext

from services import mcp_service
from api.mcp import MCPServerInfo as MCPServerInfoAPI

router = APIRouter(prefix="/mcp", tags=["MCP"])


@router.get(
    "/servers",
    response_model=List[MCPServerInfoAPI],
    status_code=status.HTTP_200_OK,
)
def list_all_mcp_servers(
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Return live capability info for every MCP server accessible to the user.

    Aggregates built-in persona servers, active desktop-host relays, and
    MCP server artifacts from collections the user has read access to.
    Each entry includes the live tools, resources, and prompts fetched
    from the running server. No workspace binding required.
    """
    infos = mcp_service.list_all_servers_for_user(db, auth.user_id)
    return [MCPServerInfoAPI.from_core(i) for i in infos]


@router.get(
    "/workspaces/{workspace_id}/servers",
    response_model=List[MCPServerInfoAPI],
    status_code=status.HTTP_200_OK,
)
def list_workspace_mcp_servers(
    workspace_id: str,
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Return live capability info for MCP servers reachable from a workspace.

    Reads ``application/vnd.agience.mcp-server+json`` artifacts from the
    workspace and connects to each server to fetch its current tools,
    resources, and prompts. Always includes the built-in persona servers.
    """
    infos = mcp_service.list_servers_for_workspace(db, auth.user_id, workspace_id)
    return [MCPServerInfoAPI.from_core(i) for i in infos]
