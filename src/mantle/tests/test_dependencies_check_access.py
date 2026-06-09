"""Unit tests for `services.dependencies.check_access` and `require_platform_admin`.

CRUDEASIO lives in Mantle (Arango grants collection). `check_access` is a
light-cone traversal that reads grants directly from Arango — no Origin HTTP
calls. Workspace IS A Collection IS An Artifact — all addressed by _key.

  1. Validate action against `_ACTION_FLAG_MAP` (unknown → 400).
  2. Look up the artifact in Arango (artifacts collection).
  3. Query `get_active_grants_for_principal_resource` for a direct grant on the target.
  4. If no direct grant, walk origin edges via `db_arango.get_origin_parent`
     and re-check each parent through Arango (bounded by `_MAX_ORIGIN_DEPTH`).
  5. Stop early if any edge's `propagate` mask doesn't include the action.

Mocks here patch `db_arango.get_active_grants_for_principal_resource` and
`db_arango.get_origin_parent` — no Origin HTTP boundary is involved.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from entities.grant import Grant as GrantEntity
from services.dependencies import (
    AuthContext,
    _ACTION_FLAG_MAP,
    check_access,
    require_platform_admin,
)

_ARANGO_GRANTS = "services.dependencies.db_arango.get_active_grants_for_principal_resource"
_ARANGO_PARENT = "services.dependencies.db_arango.get_origin_parent"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _user(uid: str = "user-1") -> AuthContext:
    return AuthContext(user_id=uid, principal_id=uid, principal_type="user")


def _arango_with(*docs):
    """Build a MagicMock arango_db whose `.collection("artifacts").get(key)`
    returns the matching doc (a dict carrying `_key` and any other fields)."""
    by_key = {d["_key"]: d for d in docs if d}
    db = MagicMock()
    art = MagicMock()
    art.get.side_effect = lambda key: by_key.get(key)
    db.collection.return_value = art
    return db


def _make_grant(resource_id: str, *actions: str, effect: str = "allow", grantee_id: str = "user-1") -> GrantEntity:
    """Create a GrantEntity with exactly the given CRUDEASIO flags set."""
    return GrantEntity(
        resource_id=resource_id,
        grantee_type="user",
        grantee_id=grantee_id,
        granted_by="admin",
        effect=effect,
        can_create="create" in actions,
        can_read="read" in actions,
        can_update="update" in actions,
        can_delete="delete" in actions,
        can_evict="evict" in actions,
        can_invoke="invoke" in actions,
        can_add="add" in actions,
        can_share="share" in actions,
        can_admin="admin" in actions,
    )


def _deny_grant(resource_id: str) -> GrantEntity:
    """A deny-effect grant with all flags set (triggers deny for any action)."""
    return GrantEntity(
        resource_id=resource_id,
        grantee_type="user",
        grantee_id="user-1",
        granted_by="admin",
        effect="deny",
        can_create=True, can_read=True, can_update=True, can_delete=True,
        can_evict=True, can_invoke=True, can_add=True, can_share=True, can_admin=True,
    )


def _grants_side_effect(by_resource: dict):
    """Factory for get_active_grants_for_principal_resource side_effect.

    by_resource maps resource_id → [GrantEntity, ...].
    Returns [] for unknown resource_ids.
    """
    def _lookup(db, *, grantee_id, resource_id):
        return by_resource.get(resource_id, [])
    return _lookup


# ---------------------------------------------------------------------------
# Action validation
# ---------------------------------------------------------------------------

class TestActionMapping:
    def test_unknown_action_returns_400(self):
        with pytest.raises(HTTPException) as ei:
            check_access(_user(), "art-1", "transmogrify", MagicMock())
        assert ei.value.status_code == 400
        assert "Unknown action" in ei.value.detail

    def test_action_map_covers_full_crudeasio(self):
        assert set(_ACTION_FLAG_MAP) == {
            "create", "read", "update", "delete", "evict",
            "invoke", "add", "share", "admin",
        }


# ---------------------------------------------------------------------------
# Artifact + auth resolution
# ---------------------------------------------------------------------------

class TestResolution:
    def test_missing_artifact_returns_404(self):
        db = _arango_with()
        with pytest.raises(HTTPException) as ei:
            check_access(_user(), "ghost", "read", db)
        assert ei.value.status_code == 404

    def test_missing_user_returns_404(self):
        db = _arango_with({"_key": "art-1", "root_id": "art-1"})
        anon = AuthContext(principal_id=None, principal_type="anonymous")
        with pytest.raises(HTTPException) as ei:
            check_access(anon, "art-1", "read", db)
        assert ei.value.status_code == 404


# ---------------------------------------------------------------------------
# Direct grants
# ---------------------------------------------------------------------------

class TestDirectGrants:
    def test_direct_allow_returns_grant(self):
        db = _arango_with({"_key": "col-1", "root_id": "col-1"})
        grants = _grants_side_effect({"col-1": [_make_grant("col-1", "read")]})
        with patch(_ARANGO_GRANTS, side_effect=grants):
            result = check_access(_user(), "col-1", "read", db)
        assert result.can_read is True
        assert result.can_admin is False

    def test_direct_deny_returns_404(self):
        db = _arango_with({"_key": "col-1", "root_id": "col-1"})
        grants = _grants_side_effect({"col-1": [_deny_grant("col-1")]})
        with patch(_ARANGO_GRANTS, side_effect=grants):
            with pytest.raises(HTTPException) as ei:
                check_access(_user(), "col-1", "read", db)
        assert ei.value.status_code == 404

    def test_no_grant_anywhere_returns_404(self):
        db = _arango_with({"_key": "col-1", "root_id": "col-1"})
        with (
            patch(_ARANGO_GRANTS, return_value=[]),
            patch(_ARANGO_PARENT, return_value=None),
        ):
            with pytest.raises(HTTPException) as ei:
                check_access(_user(), "col-1", "read", db)
        assert ei.value.status_code == 404

    def test_multiple_action_flags(self):
        """Grant with multiple flags surfaces all of them on the returned entity."""
        db = _arango_with({"_key": "col-1", "root_id": "col-1"})
        grants = _grants_side_effect({"col-1": [_make_grant("col-1", "read", "update", "share")]})
        with patch(_ARANGO_GRANTS, side_effect=grants):
            result = check_access(_user(), "col-1", "read", db)
        assert result.can_read is True
        assert result.can_update is True
        assert result.can_share is True
        assert result.can_delete is False


# ---------------------------------------------------------------------------
# Light-cone walk via origin edges
# ---------------------------------------------------------------------------

class TestLightConeTraversal:
    def test_grant_on_parent_via_origin_edge(self):
        db = _arango_with({"_key": "art-1", "root_id": "art-1"})
        grants = _grants_side_effect({"col-1": [_make_grant("col-1", "read")]})
        with (
            patch(_ARANGO_GRANTS, side_effect=grants),
            patch(_ARANGO_PARENT, side_effect=[("col-1", None), None]),
        ):
            result = check_access(_user(), "art-1", "read", db)
        assert result.can_read is True

    def test_propagate_mask_blocks_traversal(self):
        """An edge whose propagate mask excludes the action stops the walk
        before reaching the parent grant."""
        db = _arango_with({"_key": "art-1", "root_id": "art-1"})
        grant_lookup = MagicMock(return_value=[])
        with (
            patch(_ARANGO_GRANTS, side_effect=grant_lookup),
            # propagate mask only allows "create"; "read" is blocked.
            patch(_ARANGO_PARENT, return_value=("col-1", ["create"])),
        ):
            with pytest.raises(HTTPException) as ei:
                check_access(_user(), "art-1", "read", db)
        assert ei.value.status_code == 404
        # col-1 was never queried for grants because the edge blocked traversal.
        called_ids = [ca[1]["resource_id"] for ca in grant_lookup.call_args_list]
        assert "col-1" not in called_ids

    def test_propagate_mask_allows_listed_action(self):
        """An edge whose propagate mask includes the action lets the walk continue."""
        db = _arango_with({"_key": "art-1", "root_id": "art-1"})
        grants = _grants_side_effect({"col-1": [_make_grant("col-1", "read")]})
        with (
            patch(_ARANGO_GRANTS, side_effect=grants),
            patch(_ARANGO_PARENT, side_effect=[("col-1", ["read", "update"]), None]),
        ):
            result = check_access(_user(), "art-1", "read", db)
        assert result.can_read is True

    def test_deny_on_parent_returns_404(self):
        db = _arango_with({"_key": "art-1", "root_id": "art-1"})
        grants = _grants_side_effect({"col-1": [_deny_grant("col-1")]})
        with (
            patch(_ARANGO_GRANTS, side_effect=grants),
            patch(_ARANGO_PARENT, side_effect=[("col-1", None), None]),
        ):
            with pytest.raises(HTTPException) as ei:
                check_access(_user(), "art-1", "read", db)
        assert ei.value.status_code == 404

    def test_walk_continues_past_parent_with_no_grant(self):
        """No grant on first parent → keep walking up to grandparent."""
        db = _arango_with({"_key": "art-1", "root_id": "art-1"})
        grants = _grants_side_effect({
            "col-mid": [],
            "col-root": [_make_grant("col-root", "read")],
        })
        with (
            patch(_ARANGO_GRANTS, side_effect=grants),
            patch(_ARANGO_PARENT, side_effect=[("col-mid", None), ("col-root", None), None]),
        ):
            result = check_access(_user(), "art-1", "read", db)
        assert result.can_read is True

    def test_depth_limit_stops_walk(self):
        """The walk is bounded by _MAX_ORIGIN_DEPTH (10) — beyond that, 404."""
        from services.dependencies import _MAX_ORIGIN_DEPTH

        db = _arango_with({"_key": "art-1", "root_id": "art-1"})
        depths = []

        def fake_parent(_db, cursor):
            depths.append(cursor)
            return (f"parent-of-{cursor}", None)

        with (
            patch(_ARANGO_GRANTS, return_value=[]),
            patch(_ARANGO_PARENT, side_effect=fake_parent),
        ):
            with pytest.raises(HTTPException) as ei:
                check_access(_user(), "art-1", "read", db)
        assert ei.value.status_code == 404
        assert len(depths) == _MAX_ORIGIN_DEPTH


# ---------------------------------------------------------------------------
# require_platform_admin
# ---------------------------------------------------------------------------

class TestRequirePlatformAdmin:
    def test_no_user_returns_403(self):
        anon = AuthContext(principal_id=None, principal_type="anonymous")
        with pytest.raises(HTTPException) as ei:
            require_platform_admin(anon, MagicMock())
        assert ei.value.status_code == 403

    def test_bootstrap_operator_id_match_passes(self):
        """Matching platform.operator_id bypasses the grant check."""
        fake_settings = SimpleNamespace(get=lambda key: "user-1")
        with patch("services.platform_settings_service.settings", fake_settings):
            assert require_platform_admin(_user("user-1"), MagicMock()) == "user-1"

    def test_bootstrap_mismatch_falls_through_to_grant_check(self):
        """When operator ID doesn't match, the canonical Arango grant check runs."""
        fake_settings = SimpleNamespace(get=lambda key: "other-operator")
        auth_grant = _make_grant("authority-uuid", "update")
        with (
            patch("services.platform_settings_service.settings", fake_settings),
            patch(_ARANGO_GRANTS, return_value=[auth_grant]),
            patch("services.dependencies.get_id", return_value="authority-uuid"),
        ):
            assert require_platform_admin(_user("user-1"), MagicMock()) == "user-1"

    def test_no_grant_returns_403(self):
        fake_settings = SimpleNamespace(get=lambda key: None)
        with (
            patch("services.platform_settings_service.settings", fake_settings),
            patch(_ARANGO_GRANTS, return_value=[]),
            patch("services.dependencies.get_id", return_value="authority-uuid"),
        ):
            with pytest.raises(HTTPException) as ei:
                require_platform_admin(_user("user-1"), MagicMock())
        assert ei.value.status_code == 403

    def test_arango_failure_returns_403(self):
        """Arango unreachable → fail closed (403)."""
        fake_settings = SimpleNamespace(get=lambda key: None)
        with (
            patch("services.platform_settings_service.settings", fake_settings),
            patch(_ARANGO_GRANTS, side_effect=RuntimeError("arango down")),
            patch("services.dependencies.get_id", return_value="authority-uuid"),
        ):
            with pytest.raises(HTTPException) as ei:
                require_platform_admin(_user("user-1"), MagicMock())
        assert ei.value.status_code == 403
