"""Tests for `chorus/_shared/gateway_middleware.py` — Phase E universal MCP gateway."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Make `_shared` modules importable.
_HERE = Path(__file__).resolve().parent           # .../chorus/tests/
_CHORUS_DIR = _HERE.parent                        # .../chorus/
sys.path.insert(0, str(_CHORUS_DIR / "_shared"))
sys.path.insert(0, str(_CHORUS_DIR.parent))       # for `from kernel import ...`

import mantle_client  # noqa: E402
import gateway_middleware  # noqa: E402


_PERSONA_SLUGS = {"aria", "sage", "mantle", "iris", "astra", "verso", "seraph", "ophan", "core"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_scope(path: str, scope_type: str = "http") -> dict:
    return {
        "type": scope_type,
        "method": "POST",
        "path": path,
        "raw_path": path.encode("ascii"),
        "headers": [],
        "query_string": b"",
    }


class _FakeApp:
    """Records the (rewritten) scope it received and produces a 200 response."""

    def __init__(self) -> None:
        self.last_scope: dict | None = None
        self.called = False

    async def __call__(self, scope: dict, receive, send) -> None:
        self.called = True
        self.last_scope = scope
        if scope.get("type") == "http":
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({"type": "http.response.body", "body": b"ok"})


async def _drive(mw, scope: dict) -> list[dict]:
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    await mw(scope, receive, send)
    return sent


def _build_mw(*, persona_entries=None, artifact=None) -> tuple[gateway_middleware.UniversalMCPGatewayMiddleware, _FakeApp, MagicMock]:
    """Build a middleware with a mocked gateway client + persona map."""
    fake_app = _FakeApp()
    fake_client = MagicMock()
    fake_client.list_personas.return_value = persona_entries or []
    fake_client.get_artifact.return_value = artifact
    pmap = gateway_middleware.PersonaMap(gateway_client_factory=lambda: fake_client)
    mw = gateway_middleware.UniversalMCPGatewayMiddleware(
        fake_app,
        persona_map=pmap,
        gateway_client_factory=lambda: fake_client,
        local_persona_slugs=_PERSONA_SLUGS,
    )
    return mw, fake_app, fake_client


# ---------------------------------------------------------------------------
# is_uuid_like
# ---------------------------------------------------------------------------


def test_is_uuid_like_accepts_canonical():
    assert mantle_client.is_uuid_like("11111111-2222-3333-4444-555555555555")


def test_is_uuid_like_rejects_short():
    assert not mantle_client.is_uuid_like("aria")
    assert not mantle_client.is_uuid_like("")


def test_is_uuid_like_rejects_wrong_dash_positions():
    assert not mantle_client.is_uuid_like("1111111-12222-3333-4444-555555555555")


def test_is_uuid_like_rejects_non_hex():
    assert not mantle_client.is_uuid_like("zzzzzzzz-2222-3333-4444-555555555555")


# ---------------------------------------------------------------------------
# PersonaMap
# ---------------------------------------------------------------------------


def test_persona_map_refresh_populates_both_directions():
    fake_client = MagicMock()
    fake_client.list_personas.return_value = [
        {"slug": "aria", "client_id": "agience-server-aria", "artifact_id": "uuid-aria"},
        {"slug": "sage", "client_id": "agience-server-sage", "artifact_id": "uuid-sage"},
    ]
    pmap = gateway_middleware.PersonaMap(lambda: fake_client)
    assert pmap.refresh() is True
    assert pmap.slug_for_uuid("uuid-aria") == "aria"
    assert pmap.slug_for_uuid("uuid-sage") == "sage"
    assert pmap.loaded


def test_persona_map_refresh_returns_false_on_empty_response():
    fake_client = MagicMock()
    fake_client.list_personas.return_value = []
    pmap = gateway_middleware.PersonaMap(lambda: fake_client)
    assert pmap.refresh() is False
    assert not pmap.loaded


def test_persona_map_lazy_refresh_on_first_lookup():
    fake_client = MagicMock()
    fake_client.list_personas.return_value = [
        {"slug": "aria", "client_id": "agience-server-aria", "artifact_id": "uuid-aria"}
    ]
    pmap = gateway_middleware.PersonaMap(lambda: fake_client)
    assert not pmap.loaded
    assert pmap.slug_for_uuid("uuid-aria") == "aria"
    assert pmap.loaded
    fake_client.list_personas.assert_called_once()


def test_persona_map_slug_for_uuid_returns_none_on_initial_load_failure():
    """When the initial refresh fails, slug_for_uuid must return None after a
    single Mantle call — not two (the old double-call bug)."""
    fake_client = MagicMock()
    fake_client.list_personas.return_value = []
    pmap = gateway_middleware.PersonaMap(lambda: fake_client)
    # Use a far-future backoff to suppress the backoff guard for this test.
    with patch.object(gateway_middleware, "_REFRESH_BACKOFF_S", 0):
        result = pmap.slug_for_uuid("uuid-aria")
    assert result is None
    assert not pmap.loaded
    # Only one list_personas call despite the miss — no double-call.
    assert fake_client.list_personas.call_count == 1


def test_persona_map_backoff_after_failed_refresh():
    """After a failed refresh, subsequent calls skip the HTTP round-trip until
    the backoff window expires."""
    fake_client = MagicMock()
    fake_client.list_personas.return_value = []
    pmap = gateway_middleware.PersonaMap(lambda: fake_client)
    pmap.refresh()  # first attempt — fails, sets backoff
    assert fake_client.list_personas.call_count == 1
    pmap.refresh()  # still in backoff — must NOT call Mantle
    pmap.refresh()
    assert fake_client.list_personas.call_count == 1  # still just 1


def test_persona_map_retries_after_backoff_expires():
    """Once the backoff window passes, refresh() contacts Mantle again."""
    fake_client = MagicMock()
    fake_client.list_personas.side_effect = [
        [],  # first attempt fails
        [{"slug": "aria", "client_id": "agience-server-aria", "artifact_id": "uuid-aria"}],
    ]
    pmap = gateway_middleware.PersonaMap(lambda: fake_client)
    pmap.refresh()  # fails
    # Force the backoff to expire.
    pmap._next_retry_at = time.monotonic() - 1
    result = pmap.refresh()  # succeeds
    assert result is True
    assert pmap.loaded
    assert fake_client.list_personas.call_count == 2


def test_persona_map_double_refresh_on_miss():
    """A miss after load triggers one more refresh in case the registry grew."""
    fake_client = MagicMock()
    fake_client.list_personas.side_effect = [
        [{"slug": "aria", "client_id": "agience-server-aria", "artifact_id": "uuid-aria"}],
        [
            {"slug": "aria", "client_id": "agience-server-aria", "artifact_id": "uuid-aria"},
            {"slug": "sage", "client_id": "agience-server-sage", "artifact_id": "uuid-sage"},
        ],
    ]
    pmap = gateway_middleware.PersonaMap(lambda: fake_client)
    pmap.refresh()
    # Now ask for a UUID not in the first batch — second refresh should pick it up.
    assert pmap.slug_for_uuid("uuid-sage") == "sage"
    assert fake_client.list_personas.call_count == 2


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slug_request_passes_through():
    mw, fake_app, _ = _build_mw()
    await _drive(mw, _build_scope("/aria/mcp"))
    assert fake_app.called
    assert fake_app.last_scope["path"] == "/aria/mcp"


@pytest.mark.asyncio
async def test_uuid_request_rewrites_to_slug():
    uuid = "11111111-2222-3333-4444-555555555555"
    mw, fake_app, _ = _build_mw(
        persona_entries=[{"slug": "aria", "client_id": "agience-server-aria", "artifact_id": uuid}],
    )
    await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert fake_app.called
    assert fake_app.last_scope["path"] == "/aria/mcp"
    assert fake_app.last_scope["raw_path"] == b"/aria/mcp"


@pytest.mark.asyncio
async def test_uuid_with_path_suffix_preserved():
    """Sub-paths under /{uuid}/mcp/... are preserved in the rewrite."""
    uuid = "11111111-2222-3333-4444-555555555555"
    mw, fake_app, _ = _build_mw(
        persona_entries=[{"slug": "sage", "client_id": "agience-server-sage", "artifact_id": uuid}],
    )
    await _drive(mw, _build_scope(f"/{uuid}/mcp/messages/abc"))
    assert fake_app.called
    assert fake_app.last_scope["path"] == "/sage/mcp/messages/abc"


@pytest.mark.asyncio
async def test_unknown_uuid_returns_404():
    mw, fake_app, _ = _build_mw(persona_entries=[], artifact=None)
    sent = await _drive(mw, _build_scope("/99999999-aaaa-bbbb-cccc-dddddddddddd/mcp"))
    assert not fake_app.called
    assert sent[0]["status"] == 404


@pytest.mark.asyncio
async def test_external_kind_invokes_proxy():
    """`kind=external` artifacts are proxied to context.mcp_server.upstream_uri."""
    import gateway_middleware as _gm
    uuid = "22222222-3333-4444-5555-666666666666"
    mw, fake_app, _ = _build_mw(
        persona_entries=[],
        artifact={"context": '{"mcp_server": {"kind": "external", "upstream_uri": "https://example.com/mcp"}}'},
    )
    captured: dict = {}

    async def fake_proxy(*, scope, receive, send, upstream_uri, **_kw):
        captured["upstream_uri"] = upstream_uri
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": b'{"proxied":true}'})

    original = _gm.proxy_to_upstream
    _gm.proxy_to_upstream = fake_proxy
    try:
        sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    finally:
        _gm.proxy_to_upstream = original

    assert not fake_app.called
    assert captured["upstream_uri"] == "https://example.com/mcp"
    assert sent[0]["status"] == 200


@pytest.mark.asyncio
async def test_external_kind_with_no_upstream_uri_502():
    """An external artifact without upstream_uri is misconfigured — proxy returns 502."""
    uuid = "22222222-3333-4444-5555-aaaaaaaaaaaa"
    mw, fake_app, _ = _build_mw(
        persona_entries=[],
        artifact={"context": '{"mcp_server": {"kind": "external"}}'},  # no upstream_uri
    )
    sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert not fake_app.called
    # external_proxy.proxy_to_upstream returns 502 for missing upstream
    assert sent[0]["status"] == 502


@pytest.mark.asyncio
async def test_relay_kind_without_manager_returns_501():
    """If chorus host wasn't built with a relay_manager, kind=relay returns 501."""
    uuid = "33333333-4444-5555-6666-777777777777"
    mw, fake_app, _ = _build_mw(
        persona_entries=[],
        artifact={"context": '{"mcp_server": {"kind": "relay"}}'},
    )
    sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert not fake_app.called
    assert sent[0]["status"] == 501


def _build_mw_with_relay(*, persona_entries=None, artifact=None, user_id="user-1", forward_impl=None):
    fake_app = _FakeApp()
    fake_client = MagicMock()
    fake_client.list_personas.return_value = persona_entries or []
    fake_client.get_artifact.return_value = artifact
    fake_relay = MagicMock()
    if forward_impl is not None:
        fake_relay.forward_mcp_request = forward_impl
    pmap = gateway_middleware.PersonaMap(gateway_client_factory=lambda: fake_client)
    mw = gateway_middleware.UniversalMCPGatewayMiddleware(
        fake_app,
        persona_map=pmap,
        gateway_client_factory=lambda: fake_client,
        local_persona_slugs=_PERSONA_SLUGS,
        relay_manager=fake_relay,
        user_id_resolver=lambda scope: user_id,
    )
    return mw, fake_app, fake_relay


@pytest.mark.asyncio
async def test_relay_kind_with_manager_forwards_request():
    """With relay_manager + user_id_resolver, kind=relay forwards to manager."""
    import base64
    uuid = "33333333-4444-5555-6666-777777777777"

    async def fake_forward(**kwargs):
        # Manager.forward_mcp_request returns the unwrapped payload dict
        # (already unpacked from envelope by the manager).
        return {
            "ok": True,
            "status": 200,
            "headers": {"content-type": "application/json"},
            "body": base64.b64encode(b'{"ok":true}').decode("ascii"),
        }

    mw, fake_app, _ = _build_mw_with_relay(
        artifact={"context": '{"mcp_server": {"kind": "relay"}}'},
        forward_impl=fake_forward,
    )
    sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert sent[0]["status"] == 200
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    assert body == b'{"ok":true}'


@pytest.mark.asyncio
async def test_relay_kind_no_user_returns_401():
    """Relay dispatch needs a user identity. Anonymous → 401."""
    uuid = "33333333-4444-5555-6666-777777777777"
    mw, _fake_app, _ = _build_mw_with_relay(
        artifact={"context": '{"mcp_server": {"kind": "relay"}}'},
        user_id=None,
    )
    sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert sent[0]["status"] == 401


@pytest.mark.asyncio
async def test_relay_kind_no_active_session_returns_502():
    uuid = "33333333-4444-5555-6666-777777777777"
    async def fake_forward(**kwargs):
        raise LookupError("No active relay session for user 'user-1'")

    mw, _fake_app, _ = _build_mw_with_relay(
        artifact={"context": '{"mcp_server": {"kind": "relay"}}'},
        forward_impl=fake_forward,
    )
    sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert sent[0]["status"] == 502


@pytest.mark.asyncio
async def test_relay_kind_timeout_returns_504():
    uuid = "33333333-4444-5555-6666-777777777777"
    async def fake_forward(**kwargs):
        raise TimeoutError("Relay request timed out after 30s")

    mw, _fake_app, _ = _build_mw_with_relay(
        artifact={"context": '{"mcp_server": {"kind": "relay"}}'},
        forward_impl=fake_forward,
    )
    sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert sent[0]["status"] == 504


@pytest.mark.asyncio
async def test_unknown_kind_returns_502():
    uuid = "44444444-5555-6666-7777-888888888888"
    mw, fake_app, _ = _build_mw(
        persona_entries=[],
        artifact={"context": '{"mcp_server": {"kind": "weirdo"}}'},
    )
    sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert not fake_app.called
    assert sent[0]["status"] == 502


@pytest.mark.asyncio
async def test_persona_registered_but_not_loaded_returns_502():
    """Mantle reports a persona this Chorus image doesn't have built in."""
    uuid = "55555555-6666-7777-8888-999999999999"
    mw, fake_app, _ = _build_mw(
        persona_entries=[{"slug": "futureoperator", "client_id": "agience-server-futureoperator", "artifact_id": uuid}],
    )
    sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert not fake_app.called
    assert sent[0]["status"] == 502


@pytest.mark.asyncio
async def test_non_http_scope_passes_through():
    mw, fake_app, _ = _build_mw()
    await mw({"type": "lifespan"}, MagicMock(), MagicMock())
    assert fake_app.called


@pytest.mark.asyncio
async def test_root_path_passes_through():
    mw, fake_app, _ = _build_mw()
    await _drive(mw, _build_scope("/"))
    assert fake_app.called
    assert fake_app.last_scope["path"] == "/"


@pytest.mark.asyncio
async def test_well_known_passes_through():
    """`/.well-known/mcp` is not a UUID, falls through to the existing handler."""
    mw, fake_app, _ = _build_mw()
    await _drive(mw, _build_scope("/.well-known/mcp"))
    assert fake_app.called
    assert fake_app.last_scope["path"] == "/.well-known/mcp"


@pytest.mark.asyncio
async def test_malformed_artifact_context_returns_502():
    """If artifact.context isn't valid JSON, fall through to the unknown-kind branch."""
    uuid = "66666666-7777-8888-9999-aaaaaaaaaaaa"
    mw, fake_app, _ = _build_mw(
        persona_entries=[],
        artifact={"context": "not-json"},
    )
    sent = await _drive(mw, _build_scope(f"/{uuid}/mcp"))
    assert not fake_app.called
    assert sent[0]["status"] == 502


