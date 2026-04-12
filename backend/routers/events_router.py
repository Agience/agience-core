"""Unified /events WebSocket — Phase 2, Enterprise Eventing refactor.

Single bidirectional channel for all real-time artifact and operation events.
Clients can hold multiple subscriptions on one connection, each with its own
server-side filter.

## Protocol

### Client → Server (JSON messages)

```
{"op": "subscribe",   "id": "<client-sub-id>", "filter": {...}}
{"op": "unsubscribe", "id": "<client-sub-id>"}
{"op": "ping"}
```

Filter shape (all fields optional; empty filter matches every event the
caller is authorized to see):

```
{
  "container_id": "workspace-or-collection-id",
  "artifact_id":  "artifact-id",
  "content_type": "application/vnd.agience.operator+json",
  "event_names":  ["artifact.invoke.*", "artifact.created"]
}
```

### Server → Client (JSON messages)

```
{"ack": "<client-sub-id>"}                      # subscription confirmed
{"unack": "<client-sub-id>"}                    # unsubscription confirmed
{"pong": true}
{"event": "<name>", "payload": {...}, "sub_id": "<client-sub-id>", "ts": 1712345678.9, "event_id": "abc"}
```

### Auth

Bearer token in the `Authorization` header (same pattern as relay_router).
Browser clients that cannot set WS headers may pass `?access_token=...` as a
query parameter.

### ACL

Each delivery is filtered server-side by the authenticated user's grants.
Events whose `container_id` / `artifact_id` the caller cannot `read` are
silently dropped. (Grant-scoped filtering uses the existing
`_check_grant_permission` helper.)

This endpoint is the only real-time event surface on the platform. The
legacy per-container SSE stream (`/artifacts/{container_id}/events`) has
been removed; all clients subscribe through `/events`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.websockets import WebSocketState

from core import event_bus
from core.dependencies import get_arango_db
from services.dependencies import (
    AuthContext,
    _check_grant_permission,
    get_auth,
    resolve_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Events"])


# ---------------------------------------------------------------------------
# REST endpoint for servers to push events into the bus
# ---------------------------------------------------------------------------

class EmitEventRequest(BaseModel):
    """Body for POST /events/emit — lets MCP servers broadcast events."""
    event: str
    payload: Dict[str, Any] = {}
    container_id: Optional[str] = None
    artifact_id: Optional[str] = None


@router.post("/events/emit", status_code=204)
async def emit_event(
    body: EmitEventRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Push an event into the bus. Used by MCP persona servers to send
    real-time updates (e.g. chat token deltas) that reach the browser via
    the ``/events`` WebSocket.

    Auth: delegation JWT (persona acting on behalf of user) or server token.
    """
    await event_bus.publish_event(
        event_bus.Event(
            name=body.event,
            payload=body.payload,
            container_id=body.container_id,
            artifact_id=body.artifact_id,
            actor_id=auth.user_id or auth.principal_id,
        )
    )
    return None


# ---------------------------------------------------------------------------
# Per-subscription state
# ---------------------------------------------------------------------------

class _Subscription:
    __slots__ = ("client_id", "filter", "queue", "task")

    def __init__(
        self,
        client_id: str,
        event_filter: event_bus.EventFilter,
        queue: "asyncio.Queue[event_bus.Event]",
    ):
        self.client_id = client_id
        self.filter = event_filter
        self.queue = queue
        self.task: Optional[asyncio.Task] = None


def _parse_filter(raw: Any) -> event_bus.EventFilter:
    if not isinstance(raw, dict):
        return event_bus.EventFilter()

    event_names_raw = raw.get("event_names")
    event_names: Optional[List[str]] = None
    if isinstance(event_names_raw, list):
        event_names = [str(n) for n in event_names_raw if isinstance(n, str)]

    return event_bus.EventFilter(
        container_id=raw.get("container_id") or None,
        artifact_id=raw.get("artifact_id") or None,
        content_type=raw.get("content_type") or None,
        event_names=event_names,
    )


def _event_visible_to(auth: AuthContext, event: event_bus.Event) -> bool:
    """ACL check: does the caller hold a `read` grant that reaches this event?

    Rules:
    - If the event has no container and no artifact target, it's a platform
      event; only users with any grant can see it.
    - Otherwise, require `can_read` on the event's artifact_id or
      container_id.
    - Server / mcp-client principals see everything in their scope.
    """
    if not auth or not getattr(auth, "grants", None):
        # Server / mcp-client principals may legitimately have no user grants
        # but should still see events they produced. Filter them loosely by
        # principal id match.
        principal = getattr(auth, "principal_id", None)
        if principal and event.actor_id and str(principal) == str(event.actor_id):
            return True
        return False

    grants = list(auth.grants or [])
    if event.artifact_id and _check_grant_permission(
        grants, "read", resource_id=event.artifact_id
    ):
        return True
    if event.container_id and _check_grant_permission(
        grants, "read", resource_id=event.container_id
    ):
        return True
    # Unscoped read grant (rare; platform-wide viewers)
    if _check_grant_permission(grants, "read"):
        return True
    return False


async def _pump_subscription(
    sub: _Subscription,
    ws: WebSocket,
    auth: AuthContext,
    send_lock: asyncio.Lock,
) -> None:
    """Forward events from a subscription's queue to the WebSocket.

    Applies the per-user ACL check before sending. Exits cleanly when the
    socket closes or the task is cancelled.
    """
    try:
        while True:
            event = await sub.queue.get()
            if ws.client_state != WebSocketState.CONNECTED:
                return
            if not _event_visible_to(auth, event):
                continue
            msg = {
                "event": event.name,
                "payload": event.payload,
                "sub_id": sub.client_id,
                "ts": event.ts,
                "event_id": event.event_id,
            }
            async with send_lock:
                try:
                    await ws.send_json(msg)
                except Exception as exc:
                    logger.debug("events WS send failed (sub=%s): %s", sub.client_id, exc)
                    return
    except asyncio.CancelledError:
        return


async def _authenticate_ws(ws: WebSocket) -> Optional[AuthContext]:
    """Authenticate a WebSocket connection via Bearer header or ?access_token query param."""
    token: Optional[str] = None
    authorization = ws.headers.get("authorization") or ""
    if authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
    if not token:
        token = ws.query_params.get("access_token")
    if not token:
        await ws.close(code=4401, reason="Missing bearer token")
        return None

    try:
        arango_db = next(get_arango_db())
    except Exception as exc:
        logger.error("events WS could not acquire db session: %s", exc)
        await ws.close(code=1011, reason="Database unavailable")
        return None

    try:
        auth = resolve_auth(token, arango_db, request=None)
    except Exception as exc:
        logger.info("events WS auth rejected: %s", exc)
        await ws.close(code=4401, reason="Invalid token")
        return None

    return auth


@router.websocket("/events")
async def events_ws(websocket: WebSocket) -> None:
    """Unified bidirectional event stream.

    Accepts JSON messages matching the protocol documented at the top of
    this module.
    """
    auth = await _authenticate_ws(websocket)
    if auth is None:
        return

    await websocket.accept()

    subscriptions: Dict[str, _Subscription] = {}
    send_lock = asyncio.Lock()

    async def close_all() -> None:
        for sub in list(subscriptions.values()):
            if sub.task is not None:
                sub.task.cancel()
            try:
                await event_bus.unsubscribe_filtered(sub.queue)
            except Exception:
                pass
        subscriptions.clear()

    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                continue

            op = message.get("op")

            if op == "ping":
                async with send_lock:
                    await websocket.send_json({"pong": True})
                continue

            if op == "subscribe":
                client_id = str(message.get("id") or "")
                if not client_id:
                    async with send_lock:
                        await websocket.send_json({"error": "subscribe requires id"})
                    continue
                if client_id in subscriptions:
                    async with send_lock:
                        await websocket.send_json({"error": f"sub {client_id} already exists"})
                    continue

                event_filter = _parse_filter(message.get("filter"))
                queue = await event_bus.subscribe_filtered(event_filter)
                sub = _Subscription(client_id, event_filter, queue)
                sub.task = asyncio.create_task(
                    _pump_subscription(sub, websocket, auth, send_lock)
                )
                subscriptions[client_id] = sub

                async with send_lock:
                    await websocket.send_json({"ack": client_id})
                continue

            if op == "unsubscribe":
                client_id = str(message.get("id") or "")
                sub = subscriptions.pop(client_id, None)
                if sub is not None:
                    if sub.task is not None:
                        sub.task.cancel()
                    try:
                        await event_bus.unsubscribe_filtered(sub.queue)
                    except Exception:
                        pass
                async with send_lock:
                    await websocket.send_json({"unack": client_id})
                continue

            async with send_lock:
                await websocket.send_json({"error": f"unknown op {op!r}"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("events WS errored: %s", exc)
    finally:
        await close_all()
