"""External MCP server proxy — Phase E.1.

When the universal gateway resolves a `vnd.agience.mcp-server+json` artifact
whose `context.mcp_server.kind == "external"`, the request is forwarded to
the artifact's `upstream_uri` via httpx. This module owns that mechanic.

Auth model (initial):
    The proxy forwards the inbound `Authorization` header verbatim. For
    third-party MCP servers that the operator has registered as Agience
    artifacts, the artifact's context may eventually carry pre-arranged
    OAuth credentials — when that's wired up, this proxy will rewrite the
    `Authorization` header before forwarding. For now, naive pass-through
    keeps the surface small while the auth model is settled.

Streaming:
    httpx's `client.stream()` is used so large responses don't buffer in
    memory. MCP's streamable-http transport produces SSE; the streaming
    forward preserves that.

Failure modes:
    - Upstream URI absent → 502
    - Connection error / timeout → 502 with diagnostic body
    - Upstream returns non-2xx → forwarded as-is
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)

# Headers that must NOT be forwarded as-is. `host` would point at chorus's
# origin. `content-length` is rebuilt by httpx. Hop-by-hop headers per RFC 7230.
_HOP_BY_HOP = {
    b"host",
    b"connection",
    b"keep-alive",
    b"proxy-authenticate",
    b"proxy-authorization",
    b"te",
    b"trailers",
    b"transfer-encoding",
    b"upgrade",
    b"content-length",
}


async def _read_request_body(receive) -> bytes:
    """Drain the ASGI receive channel into a bytes buffer."""
    body = b""
    more_body = True
    while more_body:
        message = await receive()
        if message.get("type") != "http.request":
            break
        body += message.get("body", b"") or b""
        more_body = message.get("more_body", False)
    return body


def _filter_request_headers(scope_headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    """Convert ASGI scope headers to httpx-shaped dict, dropping hop-by-hop."""
    out: dict[str, str] = {}
    for raw_name, raw_value in scope_headers:
        name = raw_name.lower()
        if name in _HOP_BY_HOP:
            continue
        try:
            out[name.decode("latin-1")] = raw_value.decode("latin-1")
        except UnicodeDecodeError:
            continue
    return out


async def _send_status(send, status: int, body: bytes, content_type: str = "application/json") -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", content_type.encode("ascii")),
            (b"content-length", str(len(body)).encode("ascii")),
        ],
    })
    await send({"type": "http.response.body", "body": body})


async def proxy_to_upstream(
    *,
    scope: dict,
    receive,
    send,
    upstream_uri: str,
    timeout_s: float = 30.0,
    client_factory: Optional[callable] = None,
) -> None:
    """Forward an inbound MCP request to an external server.

    `client_factory()` returns an `httpx.AsyncClient` — defaults to
    `httpx.AsyncClient` with the given timeout. Tests pass a fixture-mocked
    client.
    """
    if not upstream_uri:
        await _send_status(send, 502, b'{"error":"external mcp server has no upstream_uri"}')
        return

    method: str = scope.get("method", "POST")
    raw_query = scope.get("query_string", b"") or b""
    target_url = upstream_uri
    if raw_query:
        join = "&" if "?" in upstream_uri else "?"
        target_url = f"{upstream_uri}{join}{raw_query.decode('latin-1')}"

    headers = _filter_request_headers(scope.get("headers") or [])
    body = await _read_request_body(receive)

    factory = client_factory or (lambda: httpx.AsyncClient(timeout=timeout_s))
    try:
        async with factory() as client:
            req = client.build_request(method, target_url, content=body, headers=headers)
            try:
                resp = await client.send(req, stream=True)
            except httpx.TimeoutException:
                await _send_status(send, 504, b'{"error":"upstream MCP server timed out"}')
                return
            except httpx.HTTPError as exc:
                log.warning("Proxy to %s failed: %s", target_url, exc)
                await _send_status(send, 502, b'{"error":"upstream MCP server unreachable"}')
                return

            # Stream response back to caller.
            outbound_headers: list[tuple[bytes, bytes]] = []
            for k, v in resp.headers.items():
                lk = k.lower().encode("latin-1")
                if lk in _HOP_BY_HOP:
                    continue
                outbound_headers.append((lk, v.encode("latin-1")))

            await send({
                "type": "http.response.start",
                "status": resp.status_code,
                "headers": outbound_headers,
            })
            try:
                async for chunk in resp.aiter_raw():
                    await send({"type": "http.response.body", "body": chunk, "more_body": True})
            finally:
                await resp.aclose()
            await send({"type": "http.response.body", "body": b"", "more_body": False})
    except Exception:
        log.exception("Unhandled error proxying MCP request to %s", target_url)
        await _send_status(send, 502, b'{"error":"proxy internal error"}')
