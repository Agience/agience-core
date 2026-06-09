"""run_search — search-flavor dispatch + the requires_feature gate.

Unit-level: the standard flavor and gate are exercised with monkeypatched
collaborators (no DB / accessor / MCP gateway needed)."""

import asyncio

import pytest
from fastapi import HTTPException

from services import search_flavors


class _Ctx:
    def __init__(self, user_id="user-1"):
        self.user_id = user_id
        self.arango_db = object()  # truthy; gate path is monkeypatched


def _run(artifact, body, ctx):
    return asyncio.run(search_flavors.run_search(artifact, body, ctx))


def test_standard_flavor_dispatches_to_standard_search(monkeypatch):
    seen = {}

    async def fake_standard(artifact, body, ctx):
        seen["called"] = True
        return {"flavor": "standard", "ok": True}

    monkeypatch.setattr(search_flavors, "standard_search", fake_standard)
    out = _run({"context": {"run": {"type": "standard"}}}, {"query_text": "hi"}, _Ctx())
    assert seen.get("called") is True
    assert out["flavor"] == "standard"


def test_premium_flavor_denied_without_entitlement(monkeypatch):
    monkeypatch.setattr("services.gate_service.has_feature", lambda db, uid, feat: False)
    art = {"context": {"run": {
        "type": "mcp-tool", "server": "agience/agience-server-beacon",
        "tool": "premium_search", "requires_feature": "beacon",
    }}}
    with pytest.raises(HTTPException) as ei:
        _run(art, {"query_text": "hi"}, _Ctx())
    assert ei.value.status_code == 403


def test_premium_entitled_but_server_unregistered_degrades_503(monkeypatch):
    monkeypatch.setattr("services.gate_service.has_feature", lambda db, uid, feat: True)
    # platform_topology has no mapping for the slug in tests → clean 503, not a crash.
    art = {"context": {"run": {
        "type": "mcp-tool", "server": "agience/agience-server-beacon",
        "tool": "premium_search", "requires_feature": "beacon",
    }}}
    with pytest.raises(HTTPException) as ei:
        _run(art, {"query_text": "hi"}, _Ctx())
    assert ei.value.status_code == 503


def test_unknown_flavor_returns_error_dict():
    out = _run({"context": {"run": {"type": "bogus"}}}, {}, _Ctx())
    assert "error" in out


def test_mcp_tool_flavor_missing_server_or_tool():
    out = _run({"context": {"run": {"type": "mcp-tool"}}}, {}, _Ctx())
    assert "error" in out
