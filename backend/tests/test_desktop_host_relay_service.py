from __future__ import annotations

import asyncio

from services.desktop_host_relay_service import relay_manager


class WebSocketStub:
    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, payload: dict):
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str | None = None):
        self.closed = True


async def _exercise_manager_roundtrip():
    websocket = WebSocketStub()
    session = await relay_manager.connect_session(websocket, user_id="user-1", client_id="desktop-host")
    try:
        hello = relay_manager.server_hello(session)
        assert hello["type"] == "server_hello"

        await relay_manager.handle_message(
            session.session_id,
            {
                "type": "client_hello",
                "payload": {
                    "device_id": "dev-1",
                    "display_name": "Test Host",
                    "capabilities": {"tools": True},
                },
            },
        )

        task = asyncio.create_task(
            relay_manager.invoke_tool_for_user(
                user_id="user-1",
                workspace_id="ws-1",
                server_id="desktop-host",
                tool_name="host_status",
                arguments={},
                timeout_ms=1000,
            )
        )
        await asyncio.sleep(0)
        request = websocket.sent[0]
        await relay_manager.handle_message(
            session.session_id,
            {
                "type": "tool_result",
                "payload": {
                    "request_id": request["payload"]["request_id"],
                    "ok": True,
                    "result": {"ok": True},
                    "error": None,
                },
            },
        )
        result = await task
        assert result == {"ok": True}
    finally:
        await relay_manager.disconnect_session(session.session_id)


def test_desktop_host_relay_service_roundtrip():
    asyncio.run(_exercise_manager_roundtrip())