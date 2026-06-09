"""Tests for the `mcp_request` envelope handler in `agience_relay_host.relay_runtime`.

Phase E.2: the Chorus universal-gateway relay dispatch sends `mcp_request`
envelopes; the desktop runtime translates them to local stdio MCP server
JSON-RPC and wraps the result back into `mcp_response`.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock



_HERE = Path(__file__).resolve().parent
_DESKTOP_ROOT = _HERE.parent
sys.path.insert(0, str(_DESKTOP_ROOT))

from agience_relay_host.relay_protocol import RelayEnvelope  # noqa: E402
from agience_relay_host.relay_runtime import RelayRuntimeHandler  # noqa: E402


def _build_request_envelope(
    *,
    request_id: str = "req-1",
    server_id: str = "uuid-1",
    local_server_id: str = "",
    method: str = "tools/list",
    params: dict | None = None,
    rpc_id: int = 1,
) -> RelayEnvelope:
    """Build an `mcp_request` envelope as the Chorus gateway would send it."""
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": method,
        "params": params or {},
    }).encode("utf-8")
    return RelayEnvelope(
        type="mcp_request",
        id=request_id,
        payload={
            "server_id": server_id,
            "mcp_server": {"local_server_id": local_server_id} if local_server_id else {},
            "method": "POST",
            "path": "/mcp",
            "headers": {"content-type": "application/json"},
            "body": base64.b64encode(body).decode("ascii"),
            "deadline_ms": 30000,
        },
    )


def _decode_response_jsonrpc(envelope: RelayEnvelope) -> dict:
    """Pull the JSON-RPC dict back out of a successful mcp_response envelope."""
    assert envelope.type == "mcp_response"
    payload = envelope.payload
    assert payload["ok"] is True, payload
    body_b64 = payload["body"]
    return json.loads(base64.b64decode(body_b64))


def _service_with_local_servers(tool_listings: dict[str, list], call_results: dict[tuple[str, str], dict]) -> MagicMock:
    """Build a fake DesktopHostService that responds to local-server queries."""
    service = MagicMock()
    service.config.relay_server_id = "desktop-host"
    service.config.device_id = "test-device"
    service.config.display_name = "Test Device"
    service.local_server_manifest.return_value = []

    def _list_tools(server_id: str):
        if server_id not in tool_listings:
            raise LookupError(f"No such local server: {server_id}")
        return tool_listings[server_id]

    def _call_tool(server_id: str, tool_name: str, arguments: dict):
        key = (server_id, tool_name)
        if key not in call_results:
            raise LookupError(f"Unknown tool {tool_name} on {server_id}")
        return call_results[key]

    service.list_local_server_tools = _list_tools
    service.call_local_server_tool = _call_tool
    return service


# ---------------------------------------------------------------------------
# Routing — local_server_id present
# ---------------------------------------------------------------------------


def test_mcp_request_tools_list_routes_to_local_server():
    service = _service_with_local_servers(
        tool_listings={"local-fs": [{"name": "fs_read"}, {"name": "fs_write"}]},
        call_results={},
    )
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(
        local_server_id="local-fs",
        method="tools/list",
    )
    responses = handler.handle_message(envelope)
    assert len(responses) == 1
    rpc = _decode_response_jsonrpc(responses[0])
    assert rpc["jsonrpc"] == "2.0"
    assert rpc["result"]["tools"] == [{"name": "fs_read"}, {"name": "fs_write"}]


def test_mcp_request_tools_call_routes_to_local_server():
    service = _service_with_local_servers(
        tool_listings={"local-fs": []},
        call_results={
            ("local-fs", "fs_read"): {"content": "hello"},
        },
    )
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(
        local_server_id="local-fs",
        method="tools/call",
        params={"name": "fs_read", "arguments": {"path": "/tmp/x"}},
    )
    responses = handler.handle_message(envelope)
    rpc = _decode_response_jsonrpc(responses[0])
    assert rpc["result"] == {"content": "hello"}


def test_mcp_request_unknown_local_server_returns_error():
    service = _service_with_local_servers(tool_listings={}, call_results={})
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(
        local_server_id="missing-server",
        method="tools/list",
    )
    responses = handler.handle_message(envelope)
    payload = responses[0].payload
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOT_FOUND"


def test_mcp_request_local_server_tool_call_failure_returns_execution_error():
    service = _service_with_local_servers(
        tool_listings={"local-fs": []},
        call_results={},
    )

    def boom(server_id, tool_name, arguments):
        raise RuntimeError("permission denied")

    service.call_local_server_tool = boom
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(
        local_server_id="local-fs",
        method="tools/call",
        params={"name": "fs_read", "arguments": {}},
    )
    responses = handler.handle_message(envelope)
    payload = responses[0].payload
    assert payload["ok"] is False
    assert payload["error"]["code"] == "EXECUTION_ERROR"
    assert "permission denied" in payload["error"]["message"]


def test_mcp_request_unsupported_method_on_local_server():
    """Methods other than tools/list and tools/call return NOT_FOUND."""
    service = _service_with_local_servers(tool_listings={"local-fs": []}, call_results={})
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(
        local_server_id="local-fs",
        method="prompts/list",
    )
    responses = handler.handle_message(envelope)
    payload = responses[0].payload
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Routing — no local_server_id (falls back to desktop-host tools)
# ---------------------------------------------------------------------------


def test_mcp_request_no_local_server_id_lists_desktop_host_tools():
    service = MagicMock()
    service.config.relay_server_id = "desktop-host"
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(method="tools/list")
    responses = handler.handle_message(envelope)
    rpc = _decode_response_jsonrpc(responses[0])
    tool_names = sorted(t["name"] for t in rpc["result"]["tools"])
    # The handler's _tool_map is fixed at construction; assert the canonical six.
    assert "host_status" in tool_names
    assert "fs_list_dir" in tool_names
    assert "fs_read_text" in tool_names


def test_mcp_request_no_local_server_id_calls_desktop_host_tool():
    service = MagicMock()
    service.config.relay_server_id = "desktop-host"
    service.host_status = MagicMock(return_value={"version": "0.1.0", "ok": True})
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(
        method="tools/call",
        params={"name": "host_status", "arguments": {}},
    )
    responses = handler.handle_message(envelope)
    rpc = _decode_response_jsonrpc(responses[0])
    assert rpc["result"] == {"version": "0.1.0", "ok": True}


def test_mcp_request_no_local_server_unknown_tool_returns_not_found():
    service = MagicMock()
    service.config.relay_server_id = "desktop-host"
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(
        method="tools/call",
        params={"name": "definitely_not_a_tool", "arguments": {}},
    )
    responses = handler.handle_message(envelope)
    payload = responses[0].payload
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOT_FOUND"


def test_mcp_request_no_local_server_unsupported_method_returns_not_implemented():
    service = MagicMock()
    service.config.relay_server_id = "desktop-host"
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(method="resources/list")
    responses = handler.handle_message(envelope)
    payload = responses[0].payload
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOT_IMPLEMENTED"


# ---------------------------------------------------------------------------
# Body / shape validation
# ---------------------------------------------------------------------------


def test_mcp_request_invalid_json_returns_bad_request():
    service = MagicMock()
    handler = RelayRuntimeHandler(service)

    envelope = RelayEnvelope(
        type="mcp_request",
        id="req-1",
        payload={
            "server_id": "x",
            "mcp_server": {},
            "body": base64.b64encode(b"not-json{{{").decode("ascii"),
        },
    )
    responses = handler.handle_message(envelope)
    payload = responses[0].payload
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BAD_REQUEST"


def test_mcp_request_missing_method_returns_bad_request():
    service = MagicMock()
    handler = RelayRuntimeHandler(service)

    envelope = RelayEnvelope(
        type="mcp_request",
        id="req-1",
        payload={
            "server_id": "x",
            "mcp_server": {},
            "body": base64.b64encode(b'{"jsonrpc":"2.0","id":1}').decode("ascii"),
        },
    )
    responses = handler.handle_message(envelope)
    payload = responses[0].payload
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BAD_REQUEST"


def test_mcp_request_invalid_base64_returns_bad_request():
    service = MagicMock()
    handler = RelayRuntimeHandler(service)

    envelope = RelayEnvelope(
        type="mcp_request",
        id="req-1",
        payload={
            "server_id": "x",
            "mcp_server": {},
            "body": "not!valid!b64!@#",
        },
    )
    responses = handler.handle_message(envelope)
    payload = responses[0].payload
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BAD_REQUEST"


def test_mcp_request_response_is_correlated_by_request_id():
    """The response envelope's id must match the request envelope's id
    so the chorus side can resolve the right pending future."""
    service = MagicMock()
    service.config.relay_server_id = "desktop-host"
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(request_id="abc-correlation-id", method="tools/list")
    responses = handler.handle_message(envelope)
    assert responses[0].id == "abc-correlation-id"


def test_mcp_request_jsonrpc_id_preserved_in_response():
    """The JSON-RPC id from the request body is echoed in the result."""
    service = MagicMock()
    service.config.relay_server_id = "desktop-host"
    handler = RelayRuntimeHandler(service)

    envelope = _build_request_envelope(method="tools/list", rpc_id=42)
    responses = handler.handle_message(envelope)
    rpc = _decode_response_jsonrpc(responses[0])
    assert rpc["id"] == 42
