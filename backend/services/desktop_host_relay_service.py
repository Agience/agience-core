from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

from core import event_bus
from mcp_client.contracts import MCPServerInfo, MCPTool


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RelaySession:
    session_id: str
    user_id: str
    client_id: str | None
    websocket: WebSocket
    connected_at: str = field(default_factory=_utcnow)
    last_seen_at: str = field(default_factory=_utcnow)
    device_id: str | None = None
    display_name: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    capabilities_manifest: dict[str, Any] = field(default_factory=dict)
    pending_requests: dict[str, asyncio.Future] = field(default_factory=dict)


class DesktopHostRelayManager:
    def __init__(self):
        self._lock = RLock()
        self._sessions_by_id: dict[str, RelaySession] = {}
        self._sessions_by_user: dict[str, RelaySession] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect_session(self, websocket: WebSocket, user_id: str, client_id: str | None) -> RelaySession:
        self._loop = asyncio.get_running_loop()
        session = RelaySession(session_id=str(uuid4()), user_id=user_id, client_id=client_id, websocket=websocket)
        previous_session: RelaySession | None = None
        with self._lock:
            previous_session = self._sessions_by_user.get(user_id)
            self._sessions_by_id[session.session_id] = session
            self._sessions_by_user[user_id] = session
        if previous_session is not None and previous_session.websocket is not websocket:
            with suppress(Exception):
                await previous_session.websocket.close(code=4000, reason="Replaced by newer desktop-host session")
            await self.disconnect_session(previous_session.session_id)

        # Emit a relay.session.connected event so /events subscribers can
        # observe live desktop host attach/detach. The event carries the
        # session snapshot as its payload; the session itself is still held
        # in process memory because relay sessions are ephemeral transport
        # state, not persistent artifacts.
        await event_bus.publish_event(event_bus.Event(
            name="relay.session.connected",
            payload=self._session_to_dict(session),
            actor_id=user_id,
            content_type="application/vnd.agience.relay-session+json",
        ))
        return session

    async def disconnect_session(self, session_id: str) -> None:
        session: RelaySession | None = None
        with self._lock:
            session = self._sessions_by_id.pop(session_id, None)
            if session and self._sessions_by_user.get(session.user_id) is session:
                self._sessions_by_user.pop(session.user_id, None)
        if session is None:
            return
        for future in list(session.pending_requests.values()):
            if not future.done():
                future.set_exception(RuntimeError("Desktop host relay disconnected"))

        await event_bus.publish_event(event_bus.Event(
            name="relay.session.disconnected",
            payload=self._session_to_dict(session),
            actor_id=session.user_id,
            content_type="application/vnd.agience.relay-session+json",
        ))

    def server_hello(self, session: RelaySession) -> dict[str, Any]:
        return {
            "type": "server_hello",
            "v": 1,
            "id": str(uuid4()),
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "payload": {
                "session_id": session.session_id,
                "server_time": int(datetime.now(timezone.utc).timestamp()),
                "features": {"tools": True, "resources": False},
            },
        }

    async def handle_message(self, session_id: str, envelope: dict[str, Any]) -> dict[str, Any] | None:
        session = self.get_session_by_id(session_id)
        if session is None:
            return None
        session.last_seen_at = _utcnow()
        msg_type = str(envelope.get("type") or "")
        payload = dict(envelope.get("payload") or {})

        if msg_type == "client_hello":
            session.device_id = str(payload.get("device_id")) if payload.get("device_id") is not None else None
            session.display_name = str(payload.get("display_name")) if payload.get("display_name") is not None else None
            session.capabilities = dict(payload.get("capabilities") or {})
            session.capabilities_manifest = dict(payload.get("capabilities_manifest") or {})
            return None

        if msg_type == "ping":
            return {
                "type": "pong",
                "v": 1,
                "id": str(uuid4()),
                "ts": int(datetime.now(timezone.utc).timestamp()),
                "payload": payload,
            }

        if msg_type == "pong":
            return None

        if msg_type == "tool_result":
            request_id = str(payload.get("request_id") or "")
            future = session.pending_requests.get(request_id)
            if future is not None and not future.done():
                future.set_result(payload)
            return None

        return None

    def get_session_by_id(self, session_id: str) -> RelaySession | None:
        with self._lock:
            return self._sessions_by_id.get(session_id)

    def get_active_session(self, user_id: str) -> RelaySession | None:
        with self._lock:
            return self._sessions_by_user.get(user_id)

    def list_sessions_for_user(self, user_id: str) -> list[dict[str, Any]]:
        session = self.get_active_session(user_id)
        return [self._session_to_dict(session)] if session is not None else []

    def _session_to_dict(self, session: RelaySession) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "client_id": session.client_id,
            "device_id": session.device_id,
            "display_name": session.display_name,
            "connected_at": session.connected_at,
            "last_seen_at": session.last_seen_at,
            "capabilities": session.capabilities,
            "capabilities_manifest": session.capabilities_manifest,
        }

    async def invoke_tool_for_user(
        self,
        *,
        user_id: str,
        workspace_id: str,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int = 30_000,
    ) -> dict[str, Any]:
        session = self.get_active_session(user_id)
        if session is None:
            raise ValueError("No active desktop-host relay session for this user")

        # Gate: enforce VU limit for relay tool calls
        try:
            from core import config
            if config.BILLING_ENFORCEMENT_ENABLED:
                from schemas.arango.initialize import get_arangodb_connection
                gate_db = get_arangodb_connection(
                    host=config.ARANGO_HOST, port=config.ARANGO_PORT,
                    username=config.ARANGO_USERNAME, password=config.ARANGO_PASSWORD,
                    db_name=config.ARANGO_DATABASE,
                )
                from services import gate_service
                limits = gate_service.get_or_default_limits(gate_db, user_id)
                month = datetime.now(timezone.utc).strftime("%Y-%m")
                vu_used = gate_service.get_tally(gate_db, user_id, "vu", month)
                if limits["vu_limit"] is not None and vu_used >= limits["vu_limit"]:
                    raise ValueError(
                        f"VU limit reached ({vu_used}/{limits['vu_limit']}). "
                        "Upgrade your plan or bring your own API keys."
                    )
        except ValueError:
            raise
        except Exception:
            pass  # Don't block relay on gate errors

        request_id = str(uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        session.pending_requests[request_id] = future
        envelope = {
            "type": "invoke_tool",
            "v": 1,
            "id": str(uuid4()),
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "payload": {
                "request_id": request_id,
                "owner_user_id": user_id,
                "guest_user_id": None,
                "grant_id": None,
                "workspace_id": workspace_id,
                "server_id": server_id,
                "tool_name": tool_name,
                "arguments": arguments or {},
                "deadline_ms": timeout_ms,
            },
        }

        try:
            await session.websocket.send_json(envelope)
            payload = await asyncio.wait_for(future, timeout=timeout_ms / 1000.0)
        except asyncio.TimeoutError as exc:
            raise ValueError(f"Timed out waiting for desktop-host tool '{tool_name}'") from exc
        finally:
            session.pending_requests.pop(request_id, None)

        if not payload.get("ok"):
            error = payload.get("error") or {}
            raise ValueError(error.get("message") or f"desktop-host tool '{tool_name}' failed")

        # Record VU usage after successful relay invocation
        try:
            from core import config
            if config.BILLING_ENFORCEMENT_ENABLED:
                from schemas.arango.initialize import get_arangodb_connection
                gate_db = get_arangodb_connection(
                    host=config.ARANGO_HOST, port=config.ARANGO_PORT,
                    username=config.ARANGO_USERNAME, password=config.ARANGO_PASSWORD,
                    db_name=config.ARANGO_DATABASE,
                )
                from services import gate_service
                month = datetime.now(timezone.utc).strftime("%Y-%m")
                gate_service.add_tally(gate_db, user_id, "vu", month, 1)
        except Exception:
            pass  # Don't fail relay on tally errors

        return payload.get("result") or {}

    def invoke_tool_for_user_sync(
        self,
        *,
        user_id: str,
        workspace_id: str,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int = 30_000,
    ) -> dict[str, Any]:
        if self._loop is None:
            raise ValueError("Desktop-host relay loop is not running")
        future = asyncio.run_coroutine_threadsafe(
            self.invoke_tool_for_user(
                user_id=user_id,
                workspace_id=workspace_id,
                server_id=server_id,
                tool_name=tool_name,
                arguments=arguments,
                timeout_ms=timeout_ms,
            ),
            self._loop,
        )
        return future.result(timeout=(timeout_ms / 1000.0) + 1.0)


relay_manager = DesktopHostRelayManager()


def get_desktop_host_server_info(user_id: str) -> dict[str, Any] | None:
    session = relay_manager.get_active_session(user_id)
    if session is None:
        return None
    return relay_manager._session_to_dict(session)


def get_desktop_host_tools() -> list[MCPTool]:
    return [
        MCPTool(name="host_status", description="Return desktop host runtime status."),
        MCPTool(name="fs_list_dir", description="List allowlisted local directory entries."),
        MCPTool(name="fs_read_text", description="Read UTF-8 text from an allowlisted local file."),
        MCPTool(name="mcp_servers_list_local", description="List preapproved local MCP servers."),
        MCPTool(name="mcp_servers_start_local", description="Start a preapproved local MCP server."),
        MCPTool(name="mcp_servers_stop_local", description="Stop a preapproved local MCP server."),
    ]


def get_local_mcp_server_infos(user_id: str) -> list[MCPServerInfo]:
    session = relay_manager.get_active_session(user_id)
    if session is None:
        return []
    manifest_servers = session.capabilities_manifest.get("local_servers") or []
    infos: list[MCPServerInfo] = []
    for server in manifest_servers:
        if not isinstance(server, dict):
            continue
        tools: list[MCPTool] = []
        for tool in server.get("tools") or []:
            if not isinstance(tool, dict):
                continue
            tools.append(
                MCPTool(
                    name=str(tool.get("name") or ""),
                    description=str(tool.get("description")) if tool.get("description") is not None else None,
                    input_schema=tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else None,
                )
            )
        server_id = str(server.get("server_id") or "")
        if not server_id:
            continue
        normalized_server_id = server_id if server_id.startswith("local-mcp:") else f"local-mcp:{server_id}"
        infos.append(
            MCPServerInfo(
                server=normalized_server_id,
                tools=tools,
                status="ok",
                message=str(server.get("label") or "Connected local MCP server"),
            )
        )
    return infos