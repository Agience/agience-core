"""Unit tests for `search.mantle.LightConeResolver` (Step 2.1).

CRUDEASIO lives in Mantle (Arango grants collection). The resolver reads
grants from `db_arango.get_active_grants_for_grantee` — no Origin HTTP
calls. Tests cover:

- empty grant set → empty result
- grant with action mismatch (e.g. read-only grant for "create") → not included
- direct grant only (no descendants) → just that ID
- direct grant + descendants → union
- propagate mask blocks descendants → only direct included
- unknown action → empty
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from db import arango as db_arango
from entities.grant import Grant as GrantEntity
from search.mantle import LightConeResolver

_ARANGO_GRANTS = "db.arango.get_active_grants_for_grantee"
_ARANGO_DESCENDANTS = "db.arango.list_origin_descendants"


def _grant(resource_id: str, **flags) -> GrantEntity:
    """Build a GrantEntity with CRUDEASIO flags defaulting to False."""
    defaults = {
        "can_read": False, "can_create": False, "can_update": False,
        "can_delete": False, "can_evict": False, "can_invoke": False,
        "can_add": False, "can_share": False, "can_admin": False,
    }
    defaults.update(flags)
    return GrantEntity(
        resource_id=resource_id,
        grantee_type="user",
        grantee_id="user-1",
        granted_by="admin",
        **defaults,
    )


def test_empty_grants_returns_empty_set():
    with patch.object(db_arango, "get_active_grants_for_grantee", return_value=[]):
        resolver = LightConeResolver(db=MagicMock())
        assert resolver.resolve("user-1") == set()


def test_grant_lacking_action_flag_is_excluded():
    # Grant has can_read=False; resolving for "read" must skip it.
    with patch.object(db_arango, "get_active_grants_for_grantee",
                      return_value=[_grant("col-1", can_read=False, can_admin=True)]):
        resolver = LightConeResolver(db=MagicMock())
        assert resolver.resolve("user-1", "read") == set()


def test_unknown_action_returns_empty():
    with patch.object(db_arango, "get_active_grants_for_grantee",
                      return_value=[_grant("col-1", can_read=True)]):
        resolver = LightConeResolver(db=MagicMock())
        assert resolver.resolve("user-1", "no-such-action") == set()


def test_direct_grant_with_no_descendants():
    with (
        patch.object(db_arango, "get_active_grants_for_grantee",
                     return_value=[_grant("col-1", can_read=True)]),
        patch.object(db_arango, "list_origin_descendants", return_value=set()),
    ):
        resolver = LightConeResolver(db=MagicMock())
        assert resolver.resolve("user-1", "read") == {"col-1"}


def test_direct_grant_unions_with_descendants():
    with (
        patch.object(db_arango, "get_active_grants_for_grantee",
                     return_value=[_grant("col-1", can_read=True)]),
        patch.object(db_arango, "list_origin_descendants",
                     return_value={"art-a", "art-b", "sub-col"}),
    ):
        resolver = LightConeResolver(db=MagicMock())
        result = resolver.resolve("user-1", "read")
    assert result == {"col-1", "art-a", "art-b", "sub-col"}


def test_two_grants_descendants_unioned():
    captured = {}

    def fake_descendants(_db, root_ids, action, *, max_depth):
        captured["root_ids"] = list(root_ids)
        captured["action"] = action
        captured["max_depth"] = max_depth
        return {"x", "y"}

    with (
        patch.object(db_arango, "get_active_grants_for_grantee", return_value=[
            _grant("col-1", can_read=True),
            _grant("col-2", can_read=True),
        ]),
        patch.object(db_arango, "list_origin_descendants", side_effect=fake_descendants),
    ):
        resolver = LightConeResolver(db=MagicMock(), max_depth=4)
        result = resolver.resolve("user-1", "read")

    assert result == {"col-1", "col-2", "x", "y"}
    # The resolver passes both granted IDs to the BFS in one call.
    assert set(captured["root_ids"]) == {"col-1", "col-2"}
    assert captured["action"] == "read"
    assert captured["max_depth"] == 4


def test_action_passes_through_to_descendant_lookup():
    captured = {}

    def fake_descendants(_db, root_ids, action, *, max_depth):
        captured["action"] = action
        return set()

    with (
        patch.object(db_arango, "get_active_grants_for_grantee",
                     return_value=[_grant("col-1", can_create=True)]),
        patch.object(db_arango, "list_origin_descendants", side_effect=fake_descendants),
    ):
        resolver = LightConeResolver(db=MagicMock())
        resolver.resolve("user-1", "create")

    assert captured["action"] == "create"
