from __future__ import annotations

import base64
import json
import logging
from typing import Any, Callable

from .host_service import DesktopHostService
from .relay_protocol import RelayEnvelope, relay_error

log = logging.getLogger("agience-relay-desktop.relay-runtime")


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

        if envelope.type == "mcp_request":
            return [self._handle_mcp_request(envelope)]

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

    # ------------------------------------------------------------------
    # mcp_request — Phase E.2 Chorus universal-gateway relay dispatch
    #
    # The Chorus gateway (src/chorus/_shared/relay_manager.py) sends an
    # `mcp_request` envelope when a `vnd.agience.mcp-server+json` artifact
    # with `kind=relay` is invoked. The body carries an HTTP-shaped MCP
    # request; we translate to the local stdio MCP server's JSON-RPC and
    # wrap the result back into HTTP shape.
    #
    # Routing: `payload.mcp_server.local_server_id` selects which configured
    # local stdio server handles this request. If unset, falls back to the
    # relay's own desktop-host server (filesystem / process tools).
    # ------------------------------------------------------------------

    def _handle_mcp_request(self, envelope: RelayEnvelope) -> RelayEnvelope:
        request_id = envelope.id or ""
        payload = envelope.payload or {}
        mcp_server = dict(payload.get("mcp_server") or {})
        local_server_id = str(mcp_server.get("local_server_id") or "").strip()

        body_b64 = str(payload.get("body") or "")
        try:
            raw_body = base64.b64decode(body_b64) if body_b64 else b""
        except Exception:
            return self._mcp_response_error(request_id, "BAD_REQUEST", "Invalid base64 body")

        # Parse the body as a JSON-RPC request — that's the MCP wire format.
        try:
            jsonrpc_request = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as exc:
            return self._mcp_response_error(request_id, "BAD_REQUEST", f"Invalid JSON-RPC body: {exc}")

        method = str(jsonrpc_request.get("method") or "")
        params = dict(jsonrpc_request.get("params") or {})
        rpc_id = jsonrpc_request.get("id")

        if not method:
            return self._mcp_response_error(request_id, "BAD_REQUEST", "JSON-RPC request missing method")

        # Dispatch path: local stdio MCP server when configured.
        if local_server_id:
            try:
                result = self._dispatch_local(local_server_id, method, params)
            except LookupError as exc:
                return self._mcp_response_error(request_id, "NOT_FOUND", str(exc))
            except Exception as exc:
                log.exception("Local MCP dispatch failed (server=%s method=%s)", local_server_id, method)
                return self._mcp_response_error(request_id, "EXECUTION_ERROR", str(exc))

            return self._mcp_response_success(request_id, {"jsonrpc": "2.0", "id": rpc_id, "result": result})

        # No local_server_id — try the desktop-host's own tool surface.
        if method == "tools/list":
            return self._mcp_response_success(request_id, {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"tools": [{"name": name} for name in sorted(self._tool_map)]},
            })
        if method == "tools/call":
            tool_name = str(params.get("name") or "")
            arguments = dict(params.get("arguments") or {})
            handler = self._tool_map.get(tool_name)
            if handler is None:
                return self._mcp_response_error(
                    request_id, "NOT_FOUND", f"Unknown desktop-host tool {tool_name!r}",
                )
            try:
                result = handler(**arguments)
            except Exception as exc:
                log.exception("Desktop-host tool %s failed", tool_name)
                return self._mcp_response_error(request_id, "EXECUTION_ERROR", str(exc))
            return self._mcp_response_success(request_id, {"jsonrpc": "2.0", "id": rpc_id, "result": result})

        return self._mcp_response_error(
            request_id, "NOT_IMPLEMENTED",
            f"Method {method!r} not handled by desktop-host (no local_server_id given)",
        )

    def _dispatch_local(self, local_server_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Route a JSON-RPC method to a configured local stdio MCP server."""
        if method == "tools/list":
            tools = self.service.list_local_server_tools(local_server_id)
            return {"tools": tools}
        if method == "tools/call":
            tool_name = str(params.get("name") or "")
            arguments = dict(params.get("arguments") or {})
            return self.service.call_local_server_tool(local_server_id, tool_name, arguments)
        # Resources / prompts can be added here as the protocol expands.
        raise LookupError(f"Method {method!r} not supported on local server {local_server_id!r}")

    def _mcp_response_success(self, request_id: str, jsonrpc_payload: dict[str, Any]) -> RelayEnvelope:
        body = json.dumps(jsonrpc_payload, separators=(",", ":")).encode("utf-8")
        return RelayEnvelope(
            type="mcp_response",
            id=request_id,
            payload={
                "ok": True,
                "status": 200,
                "headers": {"content-type": "application/json"},
                "body": base64.b64encode(body).decode("ascii"),
            },
        )

    def _mcp_response_error(self, request_id: str, code: str, message: str) -> RelayEnvelope:
        return RelayEnvelope(
            type="mcp_response",
            id=request_id,
            payload={
                "ok": False,
                "error": relay_error(code, message),
            },
        )