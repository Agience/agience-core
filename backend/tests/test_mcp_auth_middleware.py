import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from mcp_server.server import MCPAuthMiddleware


async def _run_http_request(middleware, authorization_value: str):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [(b"authorization", authorization_value.encode("utf-8"))],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)
    return sent


@pytest.mark.asyncio
async def test_mcp_auth_middleware_rejects_deprecated_api_key_jwt():
    async def ok_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = MCPAuthMiddleware(ok_app)

    with patch(
        "mcp_server.server.resolve_auth",
        side_effect=HTTPException(status_code=401, detail="Deprecated API key JWT not supported"),
    ):
        sent = await _run_http_request(middleware, "Bearer exchanged-jwt")

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 401
    assert sent[1]["type"] == "http.response.body"
    body = json.loads(sent[1]["body"].decode("utf-8"))
    assert body["error"] == "Deprecated API key JWT not supported"
