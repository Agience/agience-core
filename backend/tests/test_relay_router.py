from __future__ import annotations

import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from routers.relay_router import router
from services.auth_service import create_jwt_token
from services.desktop_host_relay_service import relay_manager, get_local_mcp_server_infos


def test_relay_websocket_roundtrip_and_local_server_namespace():
    app = FastAPI()
    app.include_router(router)

    user_id = "relay-router-user"
    token = create_jwt_token({"sub": user_id, "client_id": "desktop-host"})
    headers = {"Authorization": f"Bearer {token}"}
    result_holder: dict[str, object] = {}
    error_holder: dict[str, object] = {}

    with TestClient(app) as client:
        with client.websocket_connect("/relay/v1/connect", headers=headers) as websocket:
            hello = websocket.receive_json()
            assert hello["type"] == "server_hello"

            websocket.send_json(
                {
                    "type": "client_hello",
                    "payload": {
                        "device_id": "desktop-1",
                        "display_name": "Desktop Host",
                        "capabilities": {"tools": True},
                        "capabilities_manifest": {
                            "local_servers": [
                                {
                                    "server_id": "local-mcp:sample",
                                    "label": "Sample Local MCP",
                                    "tools": [
                                        {"name": "echo", "description": "Echo input"},
                                    ],
                                }
                            ]
                        },
                    },
                }
            )

            def invoke_tool() -> None:
                try:
                    result_holder["value"] = relay_manager.invoke_tool_for_user_sync(
                        user_id=user_id,
                        workspace_id="ws-1",
                        server_id="desktop-host",
                        tool_name="host_status",
                        arguments={},
                        timeout_ms=2_000,
                    )
                except Exception as exc:  # pragma: no cover - assertion below checks this.
                    error_holder["value"] = exc

            worker = threading.Thread(target=invoke_tool)
            worker.start()

            request = websocket.receive_json()
            assert request["type"] == "invoke_tool"
            assert request["payload"]["server_id"] == "desktop-host"
            assert request["payload"]["tool_name"] == "host_status"

            websocket.send_json(
                {
                    "type": "tool_result",
                    "payload": {
                        "request_id": request["payload"]["request_id"],
                        "ok": True,
                        "result": {"mode": "host", "ok": True},
                        "error": None,
                    },
                }
            )
            worker.join(timeout=5)

            assert error_holder == {}
            assert result_holder["value"] == {"mode": "host", "ok": True}

            local_servers = get_local_mcp_server_infos(user_id)
            assert len(local_servers) == 1
            assert local_servers[0].server == "local-mcp:sample"
            assert local_servers[0].tools[0].name == "echo"


def test_relay_websocket_rejects_api_key_jwt():
    app = FastAPI()
    app.include_router(router)

    token = create_jwt_token(
        {
            "sub": "relay-router-user",
            "client_id": "service-agent",
            "api_key_id": "key-123",
            "scopes": ["resource:*:search"],
        }
    )
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/relay/v1/connect", headers=headers):
                pass

    assert exc_info.value.code == 4403