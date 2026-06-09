"""Tests for `chorus/_shared/external_proxy.py` — Phase E.1 external dispatch."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


_HERE = Path(__file__).resolve().parent
_CHORUS_DIR = _HERE.parent
sys.path.insert(0, str(_CHORUS_DIR / "_shared"))
sys.path.insert(0, str(_CHORUS_DIR.parent))

import external_proxy  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scope(method: str = "POST", query: bytes = b"", headers: list | None = None) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": "/some/path",
        "raw_path": b"/some/path",
        "headers": headers or [(b"content-type", b"application/json"), (b"host", b"chorus.test")],
        "query_string": query,
    }


async def _receive_factory(body: bytes):
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _make_send():
    messages: list[dict] = []

    async def send(message: dict) -> None:
        messages.append(message)

    return messages, send


def _fake_async_response(*, status_code: int = 200, content: bytes = b'{"ok":true}', headers: dict | None = None):
    """Build a mock httpx.Response that supports `aiter_raw()` and `aclose()`."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = httpx.Headers(headers or {"content-type": "application/json"})

    async def aiter_raw():
        yield content

    resp.aiter_raw = aiter_raw
    resp.aclose = AsyncMock()
    return resp


def _client_factory_returning(resp):
    """Factory returning an async-context-manager-compatible mocked AsyncClient."""

    @asynccontextmanager
    async def factory():
        client = MagicMock()
        client.build_request = MagicMock(return_value="REQ")
        client.send = AsyncMock(return_value=resp)
        yield client

    return factory


def _client_factory_raising(exc: Exception):
    @asynccontextmanager
    async def factory():
        client = MagicMock()
        client.build_request = MagicMock(return_value="REQ")
        client.send = AsyncMock(side_effect=exc)
        yield client

    return factory


# ---------------------------------------------------------------------------
# Header filtering
# ---------------------------------------------------------------------------


def test_filter_request_headers_drops_hop_by_hop():
    headers = [
        (b"content-type", b"application/json"),
        (b"host", b"chorus.test"),
        (b"connection", b"keep-alive"),
        (b"authorization", b"Bearer abc"),
        (b"transfer-encoding", b"chunked"),
    ]
    out = external_proxy._filter_request_headers(headers)
    assert out == {"content-type": "application/json", "authorization": "Bearer abc"}


# ---------------------------------------------------------------------------
# Proxy mechanic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_upstream_uri_returns_502():
    receive = await _receive_factory(b"")
    messages, send = _make_send()
    await external_proxy.proxy_to_upstream(scope=_scope(), receive=receive, send=send, upstream_uri="")
    assert messages[0]["status"] == 502
    assert b"upstream_uri" in messages[1]["body"]


@pytest.mark.asyncio
async def test_happy_path_forwards_and_returns_response():
    receive = await _receive_factory(b'{"hello":"world"}')
    messages, send = _make_send()
    resp = _fake_async_response(status_code=200, content=b'{"reply":"ok"}')
    factory = _client_factory_returning(resp)

    await external_proxy.proxy_to_upstream(
        scope=_scope(),
        receive=receive,
        send=send,
        upstream_uri="https://example.com/mcp",
        client_factory=factory,
    )

    # Status forwarded
    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 200
    # Content streamed back
    bodies = [m["body"] for m in messages if m["type"] == "http.response.body"]
    assert b'{"reply":"ok"}' in b"".join(bodies)


@pytest.mark.asyncio
async def test_query_string_appended_to_upstream():
    """`?foo=bar` on the inbound request gets forwarded."""
    captured_url = []

    @asynccontextmanager
    async def factory():
        client = MagicMock()
        def build_request(method, url, **kwargs):
            captured_url.append(url)
            return "REQ"
        client.build_request = build_request
        client.send = AsyncMock(return_value=_fake_async_response())
        yield client

    receive = await _receive_factory(b"")
    messages, send = _make_send()
    await external_proxy.proxy_to_upstream(
        scope=_scope(query=b"foo=bar"),
        receive=receive,
        send=send,
        upstream_uri="https://example.com/mcp",
        client_factory=factory,
    )
    assert captured_url == ["https://example.com/mcp?foo=bar"]


@pytest.mark.asyncio
async def test_query_string_appended_when_url_already_has_query():
    """If `upstream_uri` already has `?x=y`, query string joins with `&`."""
    captured_url = []

    @asynccontextmanager
    async def factory():
        client = MagicMock()
        def build_request(method, url, **kwargs):
            captured_url.append(url)
            return "REQ"
        client.build_request = build_request
        client.send = AsyncMock(return_value=_fake_async_response())
        yield client

    receive = await _receive_factory(b"")
    messages, send = _make_send()
    await external_proxy.proxy_to_upstream(
        scope=_scope(query=b"foo=bar"),
        receive=receive,
        send=send,
        upstream_uri="https://example.com/mcp?session=42",
        client_factory=factory,
    )
    assert captured_url == ["https://example.com/mcp?session=42&foo=bar"]


@pytest.mark.asyncio
async def test_timeout_returns_504():
    receive = await _receive_factory(b"")
    messages, send = _make_send()
    factory = _client_factory_raising(httpx.TimeoutException("timeout"))

    await external_proxy.proxy_to_upstream(
        scope=_scope(),
        receive=receive,
        send=send,
        upstream_uri="https://example.com/mcp",
        client_factory=factory,
    )
    assert messages[0]["status"] == 504


@pytest.mark.asyncio
async def test_connection_error_returns_502():
    receive = await _receive_factory(b"")
    messages, send = _make_send()
    factory = _client_factory_raising(httpx.ConnectError("refused"))

    await external_proxy.proxy_to_upstream(
        scope=_scope(),
        receive=receive,
        send=send,
        upstream_uri="https://example.com/mcp",
        client_factory=factory,
    )
    assert messages[0]["status"] == 502


@pytest.mark.asyncio
async def test_authorization_header_passes_through():
    """Bearer tokens on inbound requests are forwarded verbatim."""
    captured_headers = []

    @asynccontextmanager
    async def factory():
        client = MagicMock()
        def build_request(method, url, **kwargs):
            captured_headers.append(kwargs.get("headers", {}))
            return "REQ"
        client.build_request = build_request
        client.send = AsyncMock(return_value=_fake_async_response())
        yield client

    receive = await _receive_factory(b"")
    messages, send = _make_send()
    await external_proxy.proxy_to_upstream(
        scope=_scope(headers=[
            (b"content-type", b"application/json"),
            (b"authorization", b"Bearer user-token-xyz"),
            (b"host", b"chorus.test"),
        ]),
        receive=receive,
        send=send,
        upstream_uri="https://example.com/mcp",
        client_factory=factory,
    )
    assert captured_headers[0].get("authorization") == "Bearer user-token-xyz"
    # `host` was stripped
    assert "host" not in captured_headers[0]


@pytest.mark.asyncio
async def test_upstream_status_forwarded_unchanged():
    """A 4xx from upstream comes back to the caller unchanged."""
    resp = _fake_async_response(status_code=403, content=b'{"error":"forbidden"}')
    factory = _client_factory_returning(resp)

    receive = await _receive_factory(b"")
    messages, send = _make_send()
    await external_proxy.proxy_to_upstream(
        scope=_scope(),
        receive=receive,
        send=send,
        upstream_uri="https://example.com/mcp",
        client_factory=factory,
    )
    assert messages[0]["status"] == 403


@pytest.mark.asyncio
async def test_response_headers_filtered_for_hop_by_hop():
    """`transfer-encoding` etc. from upstream don't leak to caller."""
    resp = _fake_async_response(
        status_code=200,
        content=b"data",
        headers={
            "content-type": "text/plain",
            "transfer-encoding": "chunked",
            "connection": "close",
            "x-custom": "preserved",
        },
    )
    factory = _client_factory_returning(resp)

    receive = await _receive_factory(b"")
    messages, send = _make_send()
    await external_proxy.proxy_to_upstream(
        scope=_scope(),
        receive=receive,
        send=send,
        upstream_uri="https://example.com/mcp",
        client_factory=factory,
    )

    start = messages[0]
    header_keys = [name.decode() for name, _ in start["headers"]]
    assert "transfer-encoding" not in header_keys
    assert "connection" not in header_keys
    assert "x-custom" in header_keys
    assert "content-type" in header_keys
