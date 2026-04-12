"""Tests for `mcp_router.py` — Phase 7D scope.

Phase 7D removed the four action endpoints (tool call, resource read,
resource import, single-server info). They are now reached via the
unified artifact dispatch surface:

- `POST /artifacts/{server_id}/invoke`           — tool invocation
- `POST /artifacts/{server_id}/op/resources_read` — resource read
- `POST /artifacts/{server_id}/op/resources_import` — resource import

The two endpoints that remain in this router are **live capability
introspection** (they connect to each accessible MCP server and return
the live tools/resources/prompts):

- `GET /mcp/servers`
- `GET /mcp/workspaces/{id}/servers`
"""

import pytest
from unittest.mock import patch

from mcp_client.contracts import MCPServerInfo as CoreServerInfo
from mcp_client.contracts import MCPTool as CoreTool
from mcp_client.contracts import MCPResourceDesc as CoreResource


@pytest.fixture
def mock_mcp_server_info():
    """Mock MCP server info using actual contract model for compatibility."""

    return CoreServerInfo(
        server="server_123",
        tools=[CoreTool(name="fetch_repo", description="Fetch repo metadata")],
        resources=[
            CoreResource(
                id="res_1",
                kind="file",
                uri="github://repo/readme",
                title="README.md",
            )
        ],
        status="ok",
        message=None,
    )


class TestMCPLiveDiscovery:
    """The two surviving endpoints — live capability introspection."""

    @pytest.mark.asyncio
    @patch("routers.mcp_router.mcp_service")
    async def test_list_all_mcp_servers(self, mock_service, client, mock_mcp_server_info):
        """`GET /mcp/servers` returns live capability info for every accessible server."""
        mock_service.list_all_servers_for_user.return_value = [mock_mcp_server_info]

        response = await client.get("/mcp/servers")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["server"] == "server_123"
        assert data[0]["status"] == "ok"
        mock_service.list_all_servers_for_user.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.mcp_router.mcp_service")
    async def test_list_workspace_mcp_servers(self, mock_service, client, mock_mcp_server_info):
        """`GET /mcp/workspaces/{id}/servers` returns workspace-scoped live capability info."""
        mock_service.list_servers_for_workspace.return_value = [mock_mcp_server_info]

        response = await client.get("/mcp/workspaces/ws_123/servers")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["server"] == "server_123"
        assert data[0]["status"] == "ok"

    @pytest.mark.asyncio
    @patch("routers.mcp_router.mcp_service")
    async def test_list_workspace_mcp_servers_empty(self, mock_service, client):
        """Empty workspace returns an empty list, not an error."""
        mock_service.list_servers_for_workspace.return_value = []

        response = await client.get("/mcp/workspaces/ws_123/servers")

        assert response.status_code == 200
        assert response.json() == []


class TestPhase7DRemovedEndpoints:
    """Regression: the four action endpoints removed in Phase 7D must
    return non-2xx. Their replacements live under `/artifacts/{id}/invoke`
    and `/artifacts/{id}/op/{op_name}`.

    Note: the FastMCP server transport is mounted at the `/mcp` prefix, so
    unrecognized `/mcp/servers/{id}/...` sub-paths fall through to that
    transport which returns 401 (auth required for unknown MCP method).
    Any non-2xx status confirms the dedicated route is gone.
    """

    _GONE = (401, 404, 405)

    @pytest.mark.asyncio
    async def test_old_tools_call_endpoint_gone(self, client):
        response = await client.post(
            "/mcp/servers/agience-core/tools/call",
            json={"tool": "search", "arguments": {}},
        )
        assert response.status_code in self._GONE

    @pytest.mark.asyncio
    async def test_old_resources_read_endpoint_gone(self, client):
        response = await client.post(
            "/mcp/servers/agience-core/resources/read",
            json={"uri": "agience://collections/c1"},
        )
        assert response.status_code in self._GONE

    @pytest.mark.asyncio
    async def test_old_resources_import_endpoint_gone(self, client):
        response = await client.post(
            "/mcp/servers/github_mcp/resources/import",
            json={"workspace_id": "ws_123", "resources": []},
        )
        assert response.status_code in self._GONE

    @pytest.mark.asyncio
    async def test_old_server_info_endpoint_gone(self, client):
        response = await client.get("/mcp/servers/agience-core/info")
        assert response.status_code in self._GONE

    @pytest.mark.asyncio
    async def test_legacy_upsert_server_endpoint_still_gone(self, client):
        """Pre-Phase-7 regression: the user-level POST /mcp/servers (registry
        upsert) remains gone."""
        response = await client.post(
            "/mcp/servers",
            json={"id": "server_123", "label": "Test Server"},
        )
        assert response.status_code in (401, 404, 405, 422)
