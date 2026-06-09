"""Tests for the collection exporter — the inverse of the seed loader.

`exporter.export_collection` walks a collection tree (root + nested
sub-collections + containment edges) and emits the same declarative
seed dicts the loader reads back. CONTENT ONLY — grants are never exported.

The exporter is exposed as the `export` operation on the collection/workspace
types (dispatch kind `native`, target `seed_provisioning.exporter.dispatch_export`)
so it is invokable by agents/workflows, not a built-in CLI feature.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.seed_provisioning import exporter
from entities.collection import COLLECTION_CONTENT_TYPE

_DOC = "application/vnd.agience.document+json"


def _root(**kw):
    """A fake CollectionEntity (attribute access)."""
    defaults = dict(name="My Collection", description="root desc",
                    content_type=COLLECTION_CONTENT_TYPE, context={"k": "v"}, content=None)
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _member(root_id, name, *, content_type=_DOC, content=None, context=None,
            order_key=None, description=""):
    """A fake `list_collection_artifacts` row (dict access)."""
    return {
        "root_id": root_id,
        "id": root_id,
        "name": name,
        "description": description,
        "content_type": content_type,
        "context": context or {},
        "content": content,
        "order_key": order_key,
    }


# ---------------------------------------------------------------------------
# export_collection
# ---------------------------------------------------------------------------


def test_missing_collection_returns_empty():
    db = MagicMock()
    with patch.object(exporter, "get_collection_by_id", return_value=None):
        assert exporter.export_collection(db, "nope") == []


def test_flat_collection_exports_root_then_members():
    db = MagicMock()
    members = [
        _member("a1", "Alpha", content="hello", order_key="a0"),
        _member("b2", "Beta", context={"foo": 1}, order_key="a1"),
    ]
    with patch.object(exporter, "get_collection_by_id", return_value=_root()), \
         patch.object(exporter, "list_collection_artifacts", return_value=members):
        seeds = exporter.export_collection(db, "root-id", namespace="export")

    # First entry is the root collection — no containment edge.
    assert seeds[0]["content_type"] == COLLECTION_CONTENT_TYPE
    assert seeds[0]["namespace"] == "export"
    assert "edges" not in seeds[0]
    assert seeds[0]["context"] == {"k": "v"}
    root_slug = seeds[0]["slug"]

    # Members carry a contained_by origin edge back to the root slug.
    assert len(seeds) == 3
    alpha = next(s for s in seeds if s["name"] == "Alpha")
    assert alpha["content"] == "hello"
    assert alpha["edges"] == [
        {"rel": "contained_by", "to": f"export/{root_slug}", "origin": True, "order_key": "a0"}
    ]
    beta = next(s for s in seeds if s["name"] == "Beta")
    assert beta["context"] == {"foo": 1}


def test_nested_sub_collection_is_walked_recursively():
    db = MagicMock()

    def _members(_db, container_id):
        if container_id == "root-id":
            return [_member("sub-1", "Sub", content_type=COLLECTION_CONTENT_TYPE, order_key="a0")]
        if container_id == "sub-1":
            return [_member("leaf-9", "Leaf", content="x", order_key="a0")]
        return []

    with patch.object(exporter, "get_collection_by_id", return_value=_root()), \
         patch.object(exporter, "list_collection_artifacts", side_effect=_members):
        seeds = exporter.export_collection(db, "root-id")

    names = [s["name"] for s in seeds]
    assert names == ["My Collection", "Sub", "Leaf"]

    sub = next(s for s in seeds if s["name"] == "Sub")
    leaf = next(s for s in seeds if s["name"] == "Leaf")
    # Leaf's parent edge points at the sub-collection's slug, not the root's.
    assert leaf["edges"][0]["to"] == f"export/{sub['slug']}"


def test_cycle_guard_does_not_infinite_loop():
    db = MagicMock()

    def _members(_db, container_id):
        # root contains sub; sub contains root again (cycle).
        if container_id == "root-id":
            return [_member("sub-1", "Sub", content_type=COLLECTION_CONTENT_TYPE, order_key="a0")]
        if container_id == "sub-1":
            return [_member("root-id", "My Collection", content_type=COLLECTION_CONTENT_TYPE, order_key="a0")]
        return []

    with patch.object(exporter, "get_collection_by_id", return_value=_root()), \
         patch.object(exporter, "list_collection_artifacts", side_effect=_members):
        seeds = exporter.export_collection(db, "root-id")

    # Terminates; the back-reference to root is emitted once as a member but not re-walked.
    assert any(s["name"] == "Sub" for s in seeds)
    assert len(seeds) < 10


def test_no_grants_are_ever_exported():
    db = MagicMock()
    members = [_member("a1", "Alpha", order_key="a0")]
    with patch.object(exporter, "get_collection_by_id", return_value=_root()), \
         patch.object(exporter, "list_collection_artifacts", return_value=members):
        seeds = exporter.export_collection(db, "root-id")
    for seed in seeds:
        assert "grant" not in seed
        assert seed.get("type") != "grant"
        assert "principal" not in seed


# ---------------------------------------------------------------------------
# dispatch_export (native operation handler) + operation wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_export_returns_namespace_count_seeds():
    db = MagicMock()
    ctx = SimpleNamespace(arango_db=db, user_id="u1")
    members = [_member("a1", "Alpha", order_key="a0")]
    with patch.object(exporter, "get_collection_by_id", return_value=_root()), \
         patch.object(exporter, "list_collection_artifacts", return_value=members):
        result = await exporter.dispatch_export(
            {"root_id": "root-id", "content_type": COLLECTION_CONTENT_TYPE},
            {"namespace": "bank"},
            ctx,
        )
    assert result["namespace"] == "bank"
    assert result["count"] == 2
    assert result["seeds"][0]["namespace"] == "bank"


@pytest.mark.asyncio
async def test_dispatch_export_raises_without_collection_id():
    ctx = SimpleNamespace(arango_db=MagicMock(), user_id="u1")
    with pytest.raises(ValueError):
        await exporter.dispatch_export({}, {}, ctx)


def test_export_operation_resolves_via_native_target():
    """The collection type's `export` op must point at a target the native
    handler can resolve — proving the type.json wiring is live, not just the code."""
    from services.handler_registry import get_native_target

    target = get_native_target("seed_provisioning.exporter.dispatch_export")
    assert target is exporter.dispatch_export
