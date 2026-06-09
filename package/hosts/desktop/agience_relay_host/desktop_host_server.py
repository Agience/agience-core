from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import DesktopRelayHostConfig
from .host_service import DesktopHostService


def create_desktop_host_server(
    config: DesktopRelayHostConfig,
    service: DesktopHostService,
) -> FastMCP:
    mcp = FastMCP(
        config.relay_server_id,
        instructions=(
            "You are the Agience desktop host runtime. You expose safe local capabilities "
            "and approved local MCP server lifecycle controls for the signed-in desktop host."
        ),
    )

    @mcp.tool(description="Return local runtime status and enabled capabilities.")
    def host_status() -> dict[str, Any]:
        return service.host_status()

    @mcp.tool(description="List directory entries from an allowlisted local filesystem path.")
    def fs_list_dir(path: str) -> dict[str, Any]:
        return service.fs_list_dir(path)

    @mcp.tool(description="Read UTF-8 text from an allowlisted local file path.")
    def fs_read_text(path: str, max_bytes: int = 65536) -> dict[str, Any]:
        return service.fs_read_text(path, max_bytes=max_bytes)

    @mcp.tool(description="List preapproved local MCP servers managed by this desktop host.")
    def mcp_servers_list_local() -> dict[str, Any]:
        return service.mcp_servers_list_local()

    @mcp.tool(description="Start a preapproved local MCP server by id.")
    def mcp_servers_start_local(server_id: str) -> dict[str, Any]:
        return service.mcp_servers_start_local(server_id)

    @mcp.tool(description="Stop a preapproved local MCP server by id.")
    def mcp_servers_stop_local(server_id: str) -> dict[str, Any]:
        return service.mcp_servers_stop_local(server_id)

    return mcp