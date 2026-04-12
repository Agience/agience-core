"""Regression tests: old MCP registry endpoints are removed.

The user-level MCP server registry was replaced by the artifact-native model.
MCP server config is now stored as application/vnd.agience.mcp-server+json
artifacts via standard artifact CRUD.

These tests assert that the old routes no longer return a successful response so
we catch any accidental re-introduction.  Note: the FastMCP transport is mounted
at the /mcp prefix, so unrecognised sub-paths may return 4xx or 5xx rather
than a strict 404 -- any non-2xx status confirms the route is gone.
"""
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from httpx import AsyncClient


def _fail_auth(*args, **kwargs):
    raise HTTPException(status_code=401, detail="Invalid token")


@pytest.fixture(autouse=True)
def mock_mcp_auth():
    """Prevent the MCP auth middleware from hitting ArangoDB during these tests."""
    with patch("mcp_server.server.resolve_auth", side_effect=_fail_auth):
        yield


@pytest.mark.asyncio
@patch("routers.mcp_router.mcp_service.list_all_servers_for_user", return_value=[])
async def test_list_servers_route_exists(mock_list, client: AsyncClient):
    """GET /mcp/servers is now a valid workspace-independent endpoint."""
    # The route exists but may return an error due to mock dependencies;
    # the key assertion is that it's no longer 404/410 (i.e., it's routed).
    resp = await client.get("/mcp/servers", headers={"Authorization": "Bearer fake-token"})
    # Auth override in conftest returns user-123, so the route is hit.
    # It may error due to mocked arango_db, but it should be routed (not 404).
    assert resp.status_code != 404


@pytest.mark.asyncio
async def test_old_upsert_server_route_gone(client: AsyncClient):
    resp = await client.post(
        "/mcp/servers",
        headers={"Authorization": "Bearer fake-token"},
        json={"id": "s1", "label": "x", "transport": {"type": "http"}},
    )
    assert resp.status_code not in (200, 201)


@pytest.mark.asyncio
async def test_old_attach_route_gone(client: AsyncClient):
    resp = await client.post(
        "/mcp/workspaces/w1/servers/attach",
        headers={"Authorization": "Bearer fake-token"},
        json={"server": "s1"},
    )
    assert resp.status_code not in (200, 201)


@pytest.mark.asyncio
async def test_old_detach_route_gone(client: AsyncClient):
    resp = await client.delete(
        "/mcp/workspaces/w1/servers/s1",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert resp.status_code not in (200, 201)
