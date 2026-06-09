"""End-to-end smoke for search-as-artifact.

Invokes a `vnd.agience.search+json` artifact through the **real**
`operation_dispatcher` and asserts it routes: type.json `operations.invoke`
→ native target `services.search_flavors.run_search` → dispatch-by-`context.run`
→ the selected flavor. Exercises the novel wiring (type resolution, native-target
import, flavor selection, the `requires_feature` gate) — mocking only the
encrypted-search accessor (tests never touch a real Oracle/S3/Arango).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from entities.grant import Grant as GrantEntity
from services import operation_dispatcher
from services.operation_dispatcher import DispatchContext

_SEARCH_CT = "application/vnd.agience.search+json"


@pytest.fixture(autouse=True)
def _builtin_handlers():
    # main.py registers these in lifespan; tests don't run lifespan, so do it here.
    from services.handler_registry import register_builtin_handlers
    register_builtin_handlers()


def _ctx(artifact_id="search-std"):
    grant = GrantEntity(
        resource_id=artifact_id, grantee_type="user", grantee_id="u1", granted_by="u1",
        can_create=True, can_read=True, can_update=True, can_delete=True, can_evict=True,
        can_invoke=True, can_add=True, can_share=True, can_admin=True,
    )
    return DispatchContext(user_id="u1", actor_id="u1", grants=[grant], arango_db=MagicMock())


def _artifact(run, artifact_id="search-std"):
    return {
        "_key": artifact_id, "root_id": artifact_id,
        "content_type": _SEARCH_CT, "context": {"run": run},
    }


def _fake_accessor_with_hits():
    hit = SimpleNamespace(doc_id="d1", score=0.9, root_id="r1", collection_id="c1", title="Doc 1")
    acc = MagicMock()
    acc.search.return_value = SimpleNamespace(hits=[hit], total=1, used_hybrid=True)
    return acc


@pytest.mark.asyncio
async def test_standard_flavor_routes_through_dispatcher_to_run_search():
    art = _artifact({"type": "standard"})
    with patch("search.mantle.wiring.build_sse_search_accessor", return_value=_fake_accessor_with_hits()):
        out = await operation_dispatcher.dispatch("invoke", art, {"query_text": "agent"}, _ctx())
    assert out["flavor"] == "standard"
    assert out["total"] == 1
    assert out["hits"][0]["id"] == "d1"


@pytest.mark.asyncio
async def test_premium_flavor_denied_without_entitlement():
    art = _artifact({
        "type": "mcp-tool", "server": "agience/agience-server-beacon",
        "tool": "premium_search", "requires_feature": "beacon",
    })
    with patch("services.gate_service.has_feature", return_value=False):
        with pytest.raises(HTTPException) as ei:
            await operation_dispatcher.dispatch("invoke", art, {"query_text": "x"}, _ctx())
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_premium_flavor_entitled_but_server_unregistered_degrades_503():
    art = _artifact({
        "type": "mcp-tool", "server": "agience/agience-server-beacon",
        "tool": "premium_search", "requires_feature": "beacon",
    })
    # Entitled, but the Beacon server slug isn't registered in tests → clean 503.
    with patch("services.gate_service.has_feature", return_value=True):
        with pytest.raises(HTTPException) as ei:
            await operation_dispatcher.dispatch("invoke", art, {"query_text": "x"}, _ctx())
    assert ei.value.status_code == 503
