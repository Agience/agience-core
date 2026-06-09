"""Chorus-side relay session manager — Phase E.2.

When a `vnd.agience.mcp-server+json` artifact has `context.mcp_server.kind = "relay"`,
the MCP request is forwarded over an active WebSocket to the user's desktop runtime.
This module owns those session objects and the request/response correlation.

Protocol envelope (Chorus ⇄ desktop runtime):

    Server → desktop:
        {
          "type":  "mcp_request",
          "v":     1,
          "id":    "<request_id>",          # uuid4 — correlates response
          "ts":    1730000000,
          "payload": {
              "server_id":  "<artifact_uuid>",
              "method":     "POST",
              "path":       "/mcp",
              "headers":    { "content-type": "application/json", ... },
              "body":       "<base64 of inbound body>",
              "deadline_ms": 30000,
          }
        }

    Desktop → server (response):
        {
          "type":   "mcp_response",
          "v":      1,
          "id":     "<request_id>",
          "ts":     ...,
          "ok":     true,
          "payload": {
              "status":  200,
              "headers": { "content-type": "application/json" },
              "body":    "<base64 of upstream body>",
          }
        }

    Or on error:
        {
          "type":   "mcp_response",
          "v":      1,
          "id":     "<request_id>",
          "ok":     false,
          "error":  { "code": "...", "message": "..." }
        }

Session lifecycle:
  - desktop runtime opens WS to `/relay/v1/connect` with a Bearer token
  - server validates the token (user identity verified upstream)
  - session is registered in the manager keyed by `(user_id, server_id?)`
  - subsequent /{server_id}/mcp requests with kind=relay are forwarded
  - desktop disconnect → session is dropped; in-flight requests time out
"""
from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class RelaySession:
    session_id: str
    user_id: str
    websocket: Any                                  # starlette WebSocket; typed as Any to avoid import in tests
    connected_at: str
    pending_requests: dict[str, asyncio.Future] = field(default_factory=dict)


class RelayManager:
    """In-memory session registry.

    One process holds active WebSocket sessions. Multi-instance Chorus
    deployments would need either sticky routing or a shared session store
    (Redis, etc.) — that's deferred to deployment scaling work.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, RelaySession] = {}
        self._sessions_by_user: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: Any, *, user_id: str) -> RelaySession:
        await websocket.accept()
        session = RelaySession(
            session_id=str(uuid4()),
            user_id=user_id,
            websocket=websocket,
            connected_at=datetime.now(timezone.utc).isoformat(),
        )
        self._sessions[session.session_id] = session
        self._sessions_by_user.setdefault(user_id, set()).add(session.session_id)
        logger.info("Relay session connected: user=%s session=%s", user_id, session.session_id)
        return session

    async def disconnect(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        # Cancel any in-flight requests waiting on this session.
        for fut in session.pending_requests.values():
            if not fut.done():
                fut.set_exception(RuntimeError("Relay session disconnected"))
        session.pending_requests.clear()
        # Drop from per-user index
        user_sessions = self._sessions_by_user.get(session.user_id)
        if user_sessions is not None:
            user_sessions.discard(session_id)
            if not user_sessions:
                self._sessions_by_user.pop(session.user_id, None)
        logger.info("Relay session disconnected: user=%s session=%s", session.user_id, session_id)

    def get_session(self, session_id: str) -> Optional[RelaySession]:
        return self._sessions.get(session_id)

    def get_active_session_for_user(self, user_id: str) -> Optional[RelaySession]:
        ids = self._sessions_by_user.get(user_id) or set()
        for session_id in ids:
            session = self._sessions.get(session_id)
            if session is not None:
                return session
        return None

    def session_count(self) -> int:
        return len(self._sessions)

    # ------------------------------------------------------------------
    # Request forwarding
    # ------------------------------------------------------------------

    async def forward_mcp_request(
        self,
        *,
        user_id: str,
        server_id: str,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
        mcp_server: Optional[dict] = None,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        """Forward an MCP request envelope over the user's active relay session.

        `mcp_server` is the artifact's `context.mcp_server` block (forwarded so
        the desktop runtime can read fields like `local_server_id`).

        Returns the desktop's response payload, or raises:
        - LookupError    if no active session exists for the user
        - TimeoutError   if the desktop doesn't respond in time
        - RuntimeError   on disconnect mid-request
        - ValueError     if the desktop returned an error envelope
        """
        session = self.get_active_session_for_user(user_id)
        if session is None:
            raise LookupError(f"No active relay session for user {user_id!r}")

        request_id = str(uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        session.pending_requests[request_id] = future

        envelope = {
            "type": "mcp_request",
            "v": 1,
            "id": request_id,
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "payload": {
                "server_id": server_id,
                "mcp_server": mcp_server or {},
                "method": method,
                "path": path,
                "headers": headers,
                "body": base64.b64encode(body).decode("ascii"),
                "deadline_ms": int(timeout_s * 1000),
            },
        }

        try:
            await session.websocket.send_json(envelope)
            response_envelope: dict[str, Any] = await asyncio.wait_for(future, timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"Relay request timed out after {timeout_s}s") from exc
        finally:
            session.pending_requests.pop(request_id, None)

        # Response shape: ok / error / status / headers / body all live inside
        # `payload` (matches the request envelope's structural symmetry and
        # fits the shared `RelayEnvelope` dataclass on the desktop side).
        response_payload = response_envelope.get("payload") or {}
        if not response_payload.get("ok"):
            err = response_payload.get("error") or {}
            raise ValueError(err.get("message") or "Relay desktop returned error envelope")
        return response_payload

    async def handle_response_envelope(self, session_id: str, envelope: dict[str, Any]) -> None:
        """Resolve the pending future for an inbound response envelope.

        Called by the WS receive loop when the desktop sends back an
        `mcp_response` keyed by request id.
        """
        if envelope.get("type") != "mcp_response":
            logger.debug("Ignoring envelope type %s on session %s", envelope.get("type"), session_id)
            return
        session = self._sessions.get(session_id)
        if session is None:
            logger.warning("Response envelope for unknown session %s", session_id)
            return
        request_id = envelope.get("id")
        if not request_id:
            logger.warning("Response envelope missing id on session %s", session_id)
            return
        future = session.pending_requests.get(str(request_id))
        if future is None or future.done():
            logger.debug("Response envelope for unknown/completed request %s", request_id)
            return
        future.set_result(envelope)


# Module-level singleton. Tests use `reset_relay_manager_for_tests()` to start fresh.
_singleton: Optional[RelayManager] = None


def get_relay_manager() -> RelayManager:
    global _singleton
    if _singleton is None:
        _singleton = RelayManager()
    return _singleton


def reset_relay_manager_for_tests() -> None:
    global _singleton
    _singleton = None
