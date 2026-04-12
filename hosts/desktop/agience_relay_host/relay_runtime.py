from __future__ import annotations

from typing import Any, Callable

from .host_service import DesktopHostService
from .relay_protocol import RelayEnvelope, relay_error


class RelayRuntimeHandler:
    def __init__(self, service: DesktopHostService):
        self.service = service
        self._tool_map: dict[str, Callable[..., dict[str, Any]]] = {
            "host_status": self.service.host_status,
            "fs_list_dir": self.service.fs_list_dir,
            "fs_read_text": self.service.fs_read_text,
            "mcp_servers_list_local": self.service.mcp_servers_list_local,
            "mcp_servers_start_local": self.service.mcp_servers_start_local,
            "mcp_servers_stop_local": self.service.mcp_servers_stop_local,
        }

    def build_client_hello(self) -> RelayEnvelope:
        return RelayEnvelope(
            type="client_hello",
            payload={
                "device_id": self.service.config.device_id,
                "display_name": self.service.config.display_name,
                "capabilities": {"tools": True, "resources": False},
                "capabilities_manifest": {
                    "server_id": self.service.config.relay_server_id,
                    "tools": sorted(self._tool_map),
                    "local_servers": self.service.local_server_manifest(),
                },
            },
        )

    def handle_message(self, envelope: RelayEnvelope) -> list[RelayEnvelope]:
        if envelope.type == "ping":
            return [RelayEnvelope(type="pong", payload=envelope.payload)]

        if envelope.type != "invoke_tool":
            return []

        payload = envelope.payload
        request_id = str(payload.get("request_id") or envelope.id or "")
        server_id = str(payload.get("server_id") or "")
        tool_name = str(payload.get("tool_name") or "")
        arguments = dict(payload.get("arguments") or {})

        if server_id.startswith("local-mcp:"):
            local_server_id = server_id.split(":", 1)[1]
            try:
                result = self.service.call_local_server_tool(local_server_id, tool_name, arguments)
                return [
                    RelayEnvelope(
                        type="tool_result",
                        payload={
                            "request_id": request_id,
                            "ok": True,
                            "result": result,
                            "error": None,
                        },
                    )
                ]
            except Exception as exc:
                return [
                    RelayEnvelope(
                        type="tool_result",
                        payload={
                            "request_id": request_id,
                            "ok": False,
                            "result": None,
                            "error": relay_error("EXECUTION_ERROR", str(exc)),
                        },
                    )
                ]

        if server_id != self.service.config.relay_server_id:
            return [
                RelayEnvelope(
                    type="tool_result",
                    payload={
                        "request_id": request_id,
                        "ok": False,
                        "result": None,
                        "error": relay_error(
                            "NOT_FOUND",
                            f"Relay runtime cannot serve server_id '{server_id}'.",
                        ),
                    },
                )
            ]

        handler = self._tool_map.get(tool_name)
        if handler is None:
            return [
                RelayEnvelope(
                    type="tool_result",
                    payload={
                        "request_id": request_id,
                        "ok": False,
                        "result": None,
                        "error": relay_error(
                            "NOT_FOUND",
                            f"Unknown desktop-host tool '{tool_name}'.",
                        ),
                    },
                )
            ]

        try:
            result = handler(**arguments)
            return [
                RelayEnvelope(
                    type="tool_result",
                    payload={
                        "request_id": request_id,
                        "ok": True,
                        "result": result,
                        "error": None,
                    },
                )
            ]
        except Exception as exc:
            return [
                RelayEnvelope(
                    type="tool_result",
                    payload={
                        "request_id": request_id,
                        "ok": False,
                        "result": None,
                        "error": relay_error("EXECUTION_ERROR", str(exc)),
                    },
                )
            ]