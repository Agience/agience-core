"""Universal MCP gateway middleware for Chorus (Phase E).

Intercepts requests of shape `/{server_id}/mcp...` where `server_id` is a
UUID. Resolves the UUID to a persona slug via a deployment-specific map
(fetched lazily from Mantle's `/internal/personas`), then rewrites the path
so the existing slug-mounted sub-app handles the request.

Persona slugs are baked into the chorus image; UUIDs are deployment-specific
random values from `platform_topology` (Mantle-side). Chorus has no way to
compute them locally — it must fetch the map.

Three dispatch kinds are wired:
  - `persona`  — local sub-app (path rewrite to slug)
  - `external` — httpx-stream proxy to `context.upstream_uri`
  - `relay`    — forward over the user's active relay WebSocket session
"""
from __future__ import annotations

import asyncio
import base64
import functools
import json
import logging
import time
from typing import Callable, Optional

from external_proxy import proxy_to_upstream  # type: ignore[import-not-found]
from mantle_client import (  # type: ignore[import-not-found]
    MantleGatewayClient,
    is_uuid_like,
)
from relay_manager import RelayManager  # type: ignore[import-not-found]

log = logging.getLogger(__name__)

# How long to wait before retrying Mantle after a failed persona-map refresh.
_REFRESH_BACKOFF_S = 30.0


class PersonaMap:
    """Cached deployment-specific slug↔UUID map populated from Mantle."""

    def __init__(self, gateway_client_factory: Callable[[], MantleGatewayClient]) -> None:
        self._client_factory = gateway_client_factory
        self._slug_to_uuid: dict[str, str] = {}
        self._uuid_to_slug: dict[str, str] = {}
        self._loaded = False
        self._next_retry_at: float = 0.0

    def refresh(self) -> bool:
        """Fetch the persona registry from Mantle. Returns True on success.

        Enforces a backoff period after a failed fetch so that a temporarily
        unreachable Mantle does not trigger a storm of outbound calls.
        """
        now = time.monotonic()
        if now < self._next_retry_at:
            # Still in backoff window — don't call Mantle again.
            return self._loaded
        try:
            personas = self._client_factory().list_personas()
        except Exception:
            log.exception("Failed to fetch persona registry from Mantle")
            self._next_retry_at = now + _REFRESH_BACKOFF_S
            return False
        if not personas:
            self._next_retry_at = now + _REFRESH_BACKOFF_S
            return False
        slug_to_uuid: dict[str, str] = {}
        uuid_to_slug: dict[str, str] = {}
        for entry in personas:
            slug = entry.get("slug")
            artifact_id = entry.get("artifact_id")
            if slug and artifact_id:
                slug_to_uuid[slug] = artifact_id
                uuid_to_slug[artifact_id] = slug
        self._slug_to_uuid = slug_to_uuid
        self._uuid_to_slug = uuid_to_slug
        self._loaded = True
        self._next_retry_at = 0.0
        log.info("Persona registry loaded: %d entries", len(slug_to_uuid))
        return True

    def slug_for_uuid(self, server_id: str) -> Optional[str]:
        """Resolve a UUID to a persona slug. Refreshes on miss."""
        if not self._loaded:
            if not self.refresh():
                # Mantle unreachable — cannot resolve yet.
                return None
        slug = self._uuid_to_slug.get(server_id)
        if slug is not None:
            return slug
        if self.refresh():
            return self._uuid_to_slug.get(server_id)
        return None

    def all_personas(self) -> list[dict]:
        return [{"slug": s, "artifact_id": u} for s, u in sorted(self._slug_to_uuid.items())]

    @property
    def loaded(self) -> bool:
        return self._loaded


class UniversalMCPGatewayMiddleware:
    """ASGI middleware: rewrites `/{server_id}/mcp...` → `/{persona_slug}/mcp...`."""

    def __init__(
        self,
        inner_app: object,
        *,
        persona_map: PersonaMap,
        gateway_client_factory: Callable[[], MantleGatewayClient],
        local_persona_slugs: set[str],
        relay_manager: Optional[RelayManager] = None,
        user_id_resolver: Optional[Callable[[dict], Optional[str]]] = None,
    ) -> None:
        self._app = inner_app
        self._map = persona_map
        self._client_factory = gateway_client_factory
        self._local_personas = local_persona_slugs
        self._relay_manager = relay_manager
        # `user_id_resolver(scope)` returns the calling user's id from the
        # inbound bearer token. Required for relay dispatch (the manager keys
        # active sessions by user). Tests inject a stub.
        self._user_id_resolver = user_id_resolver

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if not path.startswith("/"):
            await self._app(scope, receive, send)
            return

        rest = path[1:]
        first, sep, tail = rest.partition("/")
        if not sep:
            # Path has no second segment; let the index/well-known handlers serve it.
            await self._app(scope, receive, send)
            return

        if not is_uuid_like(first):
            # Not a UUID prefix — let existing slug routes handle it.
            await self._app(scope, receive, send)
            return

        # Fast path: persona resolution via the local slug↔UUID map.
        # slug_for_uuid may call Mantle (sync httpx) — run in a thread pool
        # executor so the asyncio event loop is not blocked.
        loop = asyncio.get_running_loop()
        slug = await loop.run_in_executor(None, self._map.slug_for_uuid, first)
        if slug is not None:
            if slug not in self._local_personas:
                await _send_json_status(
                    send, 502,
                    {"error": f"Persona '{slug}' is registered in Mantle but not loaded in this Chorus build"},
                )
                return
            new_path = f"/{slug}/{tail}"
            scope = {**scope, "path": new_path, "raw_path": new_path.encode("ascii")}
            await self._app(scope, receive, send)
            return

        # Not a persona — try a generic artifact lookup for external/relay kinds.
        # get_artifact is a sync httpx call — run in executor.
        artifact = await loop.run_in_executor(
            None,
            functools.partial(self._client_factory().get_artifact, first),
        )
        if artifact is None:
            await _send_json_status(send, 404, {"error": "Unknown server_id"})
            return

        try:
            context = json.loads(artifact.get("context") or "{}")
        except (ValueError, TypeError):
            context = {}
        mcp_server = context.get("mcp_server") or {}
        kind = mcp_server.get("kind", "")

        if kind == "external":
            upstream_uri = mcp_server.get("upstream_uri", "")
            await proxy_to_upstream(
                scope=scope, receive=receive, send=send, upstream_uri=upstream_uri,
            )
            return

        if kind == "relay":
            if self._relay_manager is None or self._user_id_resolver is None:
                await _send_json_status(
                    send, 501,
                    {"error": "Relay dispatch is not configured on this Chorus instance"},
                )
                return
            user_id = self._user_id_resolver(scope)
            if not user_id:
                await _send_json_status(
                    send, 401,
                    {"error": "Relay dispatch requires an authenticated user"},
                )
                return
            await _proxy_via_relay(
                scope=scope, receive=receive, send=send,
                relay_manager=self._relay_manager,
                user_id=user_id,
                server_id=first,
                mcp_server=mcp_server,
            )
            return

        await _send_json_status(send, 502, {"error": f"Unknown mcp-server kind: {kind!r}"})


async def _proxy_via_relay(
    *,
    scope: dict,
    receive,
    send,
    relay_manager: RelayManager,
    user_id: str,
    server_id: str,
    mcp_server: dict,
) -> None:
    """Forward the inbound MCP request through the user's relay WebSocket session.

    `mcp_server` is the artifact's `context.mcp_server` block. Its
    `local_server_id` field (when present) lets the desktop runtime route to
    the correct local stdio MCP server.
    """
    method: str = scope.get("method", "POST")
    path: str = scope.get("path", "")
    raw_query = scope.get("query_string", b"") or b""
    if raw_query:
        path = f"{path}?{raw_query.decode('latin-1')}"
    headers: dict[str, str] = {}
    for k, v in (scope.get("headers") or []):
        headers[k.decode("latin-1")] = v.decode("latin-1")

    # Drain inbound body
    body = b""
    more = True
    while more:
        msg = await receive()
        if msg.get("type") != "http.request":
            break
        body += msg.get("body", b"") or b""
        more = msg.get("more_body", False)

    try:
        payload = await relay_manager.forward_mcp_request(
            user_id=user_id,
            server_id=server_id,
            method=method,
            path=path,
            headers=headers,
            body=body,
            mcp_server=mcp_server,
        )
    except LookupError:
        await _send_json_status(send, 502, {"error": "No active relay session for this user"})
        return
    except TimeoutError:
        await _send_json_status(send, 504, {"error": "Relay request timed out"})
        return
    except (RuntimeError, ValueError) as exc:
        await _send_json_status(send, 502, {"error": f"Relay forward failed: {exc}"})
        return

    status_code = int(payload.get("status") or 200)
    response_headers_dict = payload.get("headers") or {}
    response_body_b64 = payload.get("body") or ""
    response_body = base64.b64decode(response_body_b64) if response_body_b64 else b""

    outbound_headers: list[tuple[bytes, bytes]] = []
    for k, v in response_headers_dict.items():
        lk = k.lower().encode("latin-1")
        if lk in (b"transfer-encoding", b"connection", b"content-length"):
            continue
        outbound_headers.append((lk, str(v).encode("latin-1")))
    outbound_headers.append((b"content-length", str(len(response_body)).encode("ascii")))

    await send({
        "type": "http.response.start",
        "status": status_code,
        "headers": outbound_headers,
    })
    await send({"type": "http.response.body", "body": response_body})


async def _send_json_status(send: object, status: int, body: dict) -> None:
    payload = json.dumps(body).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("ascii")),
        ],
    })
    await send({"type": "http.response.body", "body": payload})
