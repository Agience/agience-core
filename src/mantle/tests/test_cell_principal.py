"""The MANTLE cell-key principal is the collection's immutable origin root.

Covers :func:`db.arango.get_origin_root` (walk the origin chain to the top,
cycle/depth-guarded) and :func:`search.mantle.principal.resolve_cell_principal`
(the index path and the query path resolve the SAME principal for the same
collection, so the derived keys match). There is no "owner" / ``created_by`` in
the crypto principal.
"""

from __future__ import annotations

from unittest.mock import patch

from db import arango as db_arango
from search.mantle.principal import resolve_cell_principal


# ---------------------------------------------------------------------------
# get_origin_root — walk the immutable origin chain to the top
# ---------------------------------------------------------------------------

def test_get_origin_root_walks_to_top():
    # c -> b -> a; a is the root (no origin parent).
    chain = {"c": ("b", None), "b": ("a", None), "a": None}
    with patch.object(db_arango, "get_origin_parent", side_effect=lambda db, rid: chain.get(rid)):
        assert db_arango.get_origin_root(None, "c") == "a"
        assert db_arango.get_origin_root(None, "b") == "a"


def test_get_origin_root_self_when_no_parent():
    with patch.object(db_arango, "get_origin_parent", return_value=None):
        assert db_arango.get_origin_root(None, "solo") == "solo"


def test_get_origin_root_cycle_guarded():
    # x -> y -> x: a malformed cycle must not loop forever.
    chain = {"x": ("y", None), "y": ("x", None)}
    with patch.object(db_arango, "get_origin_parent", side_effect=lambda db, rid: chain.get(rid)):
        assert db_arango.get_origin_root(None, "x") in {"x", "y"}


def test_get_origin_root_depth_bounded():
    # A long chain past max_depth returns the deepest id reached, not an error.
    def parent(db, rid):
        n = int(rid)
        return (str(n + 1), None)  # never terminates
    with patch.object(db_arango, "get_origin_parent", side_effect=parent):
        got = db_arango.get_origin_root(None, "0", max_depth=5)
        assert got == "5"


# ---------------------------------------------------------------------------
# resolve_cell_principal — the shared index/query resolution
# ---------------------------------------------------------------------------

def test_resolve_is_origin_root():
    with patch.object(db_arango, "get_origin_root", return_value="root-1"):
        assert resolve_cell_principal(None, "col-9") == "root-1"


def test_resolve_empty_collection_is_empty():
    assert resolve_cell_principal(None, "") == ""


def test_resolve_falls_back_to_collection_on_error():
    with patch.object(db_arango, "get_origin_root", side_effect=RuntimeError("boom")):
        assert resolve_cell_principal(None, "col-9") == "col-9"


def test_index_and_query_resolve_the_same_principal():
    # The load-bearing invariant: the same collection_id resolves to the same
    # principal at index time and at query time, so the cell key matches.
    with patch.object(db_arango, "get_origin_root", return_value="root-7"):
        principal_at_index = resolve_cell_principal(None, "col-A")
        principal_at_query = resolve_cell_principal(None, "col-A")
        assert principal_at_index == principal_at_query == "root-7"


def test_principal_is_not_created_by():
    # Two artifacts in the same collection created by different people must land
    # under the SAME principal (the collection's origin root) — never created_by.
    with patch.object(db_arango, "get_origin_root", return_value="col-root"):
        # Same collection regardless of who created the artifact.
        assert resolve_cell_principal(None, "shared-col") == "col-root"
