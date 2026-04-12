from __future__ import annotations

from typing import Any

from .config import DesktopRelayHostConfig
from .local_policy import LocalPolicy
from .supervisor import LocalServerSupervisor


class DesktopHostService:
    def __init__(
        self,
        config: DesktopRelayHostConfig,
        policy: LocalPolicy,
        supervisor: LocalServerSupervisor,
    ):
        self.config = config
        self.policy = policy
        self.supervisor = supervisor

    def host_status(self) -> dict[str, Any]:
        return {
            "mode": self.config.mode.value,
            "display_name": self.config.display_name,
            "device_id": self.config.device_id,
            "relay_server_id": self.config.relay_server_id,
            "authority_url": self.config.authority_url,
            "enabled_personas": list(self.config.enabled_personas),
            "allowed_roots": [str(root) for root in self.policy.allowed_roots],
            "local_server_count": len(self.supervisor.list_servers()),
        }

    def fs_list_dir(self, path: str) -> dict[str, Any]:
        return {"path": str(self.policy.resolve_allowed_path(path)), "entries": self.policy.list_dir(path)}

    def fs_read_text(self, path: str, max_bytes: int = 65536) -> dict[str, Any]:
        return self.policy.read_text(path, max_bytes=max_bytes)

    def mcp_servers_list_local(self) -> dict[str, Any]:
        return {"servers": self.supervisor.list_servers()}

    def mcp_servers_start_local(self, server_id: str) -> dict[str, Any]:
        return self.supervisor.start_server(server_id)

    def mcp_servers_stop_local(self, server_id: str) -> dict[str, Any]:
        return self.supervisor.stop_server(server_id)

    def local_server_manifest(self) -> list[dict[str, Any]]:
        return self.supervisor.local_server_manifest()

    def call_local_server_tool(self, server_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.supervisor.call_server_tool(server_id, tool_name, arguments)