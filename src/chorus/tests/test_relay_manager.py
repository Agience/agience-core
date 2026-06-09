"""Tests for `chorus/_shared/relay_manager.py` — Phase E.2 relay dispatch."""
from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


_HERE = Path(__file__).resolve().parent
_CHORUS_DIR = _HERE.parent
sys.path.insert(0, str(_CHORUS_DIR / "_shared"))
sys.path.insert(0, str(_CHORUS_DIR.parent))

import relay_manager  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_singleton():
    relay_manager.reset_relay_manager_for_tests()
    yield
    relay_manager.reset_relay_manager_for_tests()


def _fake_websocket() -> MagicMock:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_registers_session():
    mgr = relay_manager.RelayManager()
    ws = _fake_websocket()
    session = await mgr.connect(ws, user_id="user-1")
    assert session.session_id
    assert session.user_id == "user-1"
    assert mgr.session_count() == 1
    ws.accept.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_active_session_for_user():
    mgr = relay_manager.RelayManager()
    ws = _fake_websocket()
    session = await mgr.connect(ws, user_id="user-1")

    assert mgr.get_active_session_for_user("user-1") is session
    assert mgr.get_active_session_for_user("user-2") is None


@pytest.mark.asyncio
async def test_disconnect_removes_session_and_cancels_pending():
    mgr = relay_manager.RelayManager()
    ws = _fake_websocket()
    session = await mgr.connect(ws, user_id="user-1")

    # Add a fake pending request
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    session.pending_requests["req-1"] = fut

    await mgr.disconnect(session.session_id)
    assert mgr.session_count() == 0
    assert mgr.get_active_session_for_user("user-1") is None
    # Pending future should fail with disconnect error
    assert fut.done()
    with pytest.raises(RuntimeError, match="disconnected"):
        fut.result()


@pytest.mark.asyncio
async def test_disconnect_unknown_session_is_noop():
    mgr = relay_manager.RelayManager()
    await mgr.disconnect("does-not-exist")  # must not raise


@pytest.mark.asyncio
async def test_multiple_users_isolated():
    mgr = relay_manager.RelayManager()
    ws_a = _fake_websocket()
    ws_b = _fake_websocket()
    session_a = await mgr.connect(ws_a, user_id="user-a")
    session_b = await mgr.connect(ws_b, user_id="user-b")

    assert mgr.session_count() == 2
    assert mgr.get_active_session_for_user("user-a") is session_a
    assert mgr.get_active_session_for_user("user-b") is session_b


# ---------------------------------------------------------------------------
# forward_mcp_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forward_no_active_session_raises_lookup():
    mgr = relay_manager.RelayManager()
    with pytest.raises(LookupError, match="No active relay session"):
        await mgr.forward_mcp_request(
            user_id="ghost",
            server_id="srv-1",
            method="POST", path="/mcp", headers={}, body=b"",
        )


@pytest.mark.asyncio
async def test_forward_sends_envelope_and_returns_response_payload():
    mgr = relay_manager.RelayManager()
    ws = _fake_websocket()
    session = await mgr.connect(ws, user_id="user-1")

    sent_envelopes: list = []
    async def fake_send(envelope):
        sent_envelopes.append(envelope)
        # Simulate desktop responding immediately with the right id.
        # Envelope shape matches the desktop's `RelayEnvelope` dataclass:
        # everything-but-type/id/v/ts goes inside `payload`.
        request_id = envelope["id"]
        response = {
            "type": "mcp_response",
            "v": 1,
            "id": request_id,
            "payload": {
                "ok": True,
                "status": 200,
                "headers": {"content-type": "application/json"},
                "body": base64.b64encode(b'{"result":"ok"}').decode("ascii"),
            },
        }
        # Resolve the pending future the same way the WS receive loop would
        await mgr.handle_response_envelope(session.session_id, response)
    ws.send_json = fake_send

    result = await mgr.forward_mcp_request(
        user_id="user-1",
        server_id="srv-1",
        method="POST",
        path="/mcp",
        headers={"x-test": "yes"},
        body=b'{"hello":1}',
        timeout_s=5.0,
    )

    # Envelope sanity
    assert len(sent_envelopes) == 1
    env = sent_envelopes[0]
    assert env["type"] == "mcp_request"
    assert env["payload"]["server_id"] == "srv-1"
    assert env["payload"]["method"] == "POST"
    assert env["payload"]["headers"]["x-test"] == "yes"
    assert base64.b64decode(env["payload"]["body"]) == b'{"hello":1}'

    # Response payload
    assert result["status"] == 200
    assert base64.b64decode(result["body"]) == b'{"result":"ok"}'


@pytest.mark.asyncio
async def test_forward_timeout_raises():
    mgr = relay_manager.RelayManager()
    ws = _fake_websocket()
    await mgr.connect(ws, user_id="user-1")
    # send_json succeeds but no response ever comes back

    with pytest.raises(TimeoutError, match="timed out"):
        await mgr.forward_mcp_request(
            user_id="user-1",
            server_id="srv-1",
            method="POST", path="/mcp", headers={}, body=b"",
            timeout_s=0.05,
        )


@pytest.mark.asyncio
async def test_forward_error_envelope_raises_value():
    mgr = relay_manager.RelayManager()
    ws = _fake_websocket()
    session = await mgr.connect(ws, user_id="user-1")

    async def fake_send(envelope):
        request_id = envelope["id"]
        await mgr.handle_response_envelope(session.session_id, {
            "type": "mcp_response",
            "v": 1,
            "id": request_id,
            "payload": {
                "ok": False,
                "error": {"code": "tool_failure", "message": "desktop barfed"},
            },
        })
    ws.send_json = fake_send

    with pytest.raises(ValueError, match="desktop barfed"):
        await mgr.forward_mcp_request(
            user_id="user-1",
            server_id="srv-1",
            method="POST", path="/mcp", headers={}, body=b"",
            timeout_s=5.0,
        )


@pytest.mark.asyncio
async def test_forward_disconnect_mid_request_raises_runtime():
    """If desktop disconnects while we're awaiting a response, the future fails."""
    mgr = relay_manager.RelayManager()
    ws = _fake_websocket()
    session = await mgr.connect(ws, user_id="user-1")

    # Send doesn't trigger any response.
    forward_task = asyncio.create_task(
        mgr.forward_mcp_request(
            user_id="user-1",
            server_id="srv-1",
            method="POST", path="/mcp", headers={}, body=b"",
            timeout_s=5.0,
        )
    )
    # Yield once so forward_mcp_request reaches the await
    await asyncio.sleep(0)
    await mgr.disconnect(session.session_id)

    with pytest.raises(RuntimeError, match="disconnected"):
        await forward_task


# ---------------------------------------------------------------------------
# handle_response_envelope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_response_for_unknown_session_is_noop():
    mgr = relay_manager.RelayManager()
    await mgr.handle_response_envelope("ghost-session", {
        "type": "mcp_response", "id": "x", "payload": {"ok": True},
    })  # must not raise


@pytest.mark.asyncio
async def test_handle_response_ignores_non_response_envelope_types():
    mgr = relay_manager.RelayManager()
    ws = _fake_websocket()
    session = await mgr.connect(ws, user_id="user-1")

    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    session.pending_requests["req-1"] = fut

    await mgr.handle_response_envelope(session.session_id, {
        "type": "mcp_request",  # wrong type — ignored
        "id": "req-1", "payload": {"ok": True},
    })
    assert not fut.done()


@pytest.mark.asyncio
async def test_handle_response_ignores_unknown_request_id():
    mgr = relay_manager.RelayManager()
    ws = _fake_websocket()
    session = await mgr.connect(ws, user_id="user-1")

    await mgr.handle_response_envelope(session.session_id, {
        "type": "mcp_response",
        "id": "no-such-request",
        "payload": {"ok": True},
    })  # silently dropped


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


def test_get_relay_manager_returns_singleton():
    a = relay_manager.get_relay_manager()
    b = relay_manager.get_relay_manager()
    assert a is b


def test_reset_relay_manager_for_tests():
    a = relay_manager.get_relay_manager()
    relay_manager.reset_relay_manager_for_tests()
    b = relay_manager.get_relay_manager()
    assert a is not b
