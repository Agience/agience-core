"""Tests for `mcp_router.py`.

The live capability-introspection endpoints (`GET /mcp/servers` and
`GET /mcp/workspaces/{id}/servers`) were removed. MCP server records
are now queried via:

  GET /artifacts?content_type=application/vnd.agience.mcp-server+json

Tool invocation and resource ops flow through the unified artifact surface:

  POST /artifacts/{server_id}/invoke
  POST /artifacts/{server_id}/op/resources_read
  POST /artifacts/{server_id}/op/resources_import
"""

import pytest


class TestMCPRouterNoLiveIntrospection:
    """Former live-introspection endpoints must no longer be reachable."""

    @pytest.mark.asyncio
    async def test_list_all_servers_endpoint_gone(self, client):
        """`GET /mcp/servers` was removed; query artifacts by content_type instead."""
        response = await client.get("/mcp/servers")
        assert response.status_code not in (200, 201)

    @pytest.mark.asyncio
    async def test_list_workspace_servers_endpoint_gone(self, client):
        """`GET /mcp/workspaces/{id}/servers` was removed."""
        response = await client.get("/mcp/workspaces/ws_123/servers")
        assert response.status_code not in (200, 201)


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
