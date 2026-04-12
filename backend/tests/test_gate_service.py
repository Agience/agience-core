"""Unit tests for services.gate_service.

Covers entitlement cache CRUD, free-tier defaults, usage tally accumulation,
and the AQL count queries (which are unified-store-aware after the migration
fix).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services import gate_service
from entities.collection import WORKSPACE_CONTENT_TYPE


# ---------------------------------------------------------------------------
# enforcement_enabled
# ---------------------------------------------------------------------------

class TestEnforcementEnabled:
    def test_true_when_config_flag_set(self):
        with patch("core.config.BILLING_ENFORCEMENT_ENABLED", True):
            assert gate_service.enforcement_enabled() is True

    def test_false_when_config_flag_unset(self):
        with patch("core.config.BILLING_ENFORCEMENT_ENABLED", False):
            assert gate_service.enforcement_enabled() is False


# ---------------------------------------------------------------------------
# get_limits / get_or_default_limits / set_limits
# ---------------------------------------------------------------------------

def _db_with_doc(collection_name: str, key: str, doc: dict | None):
    db = MagicMock()
    coll = MagicMock()
    coll.has.return_value = doc is not None
    coll.get.return_value = doc
    db.collection.side_effect = lambda name: coll if name == collection_name else MagicMock()
    return db, coll


class TestLimits:
    def test_get_limits_returns_none_when_no_row(self):
        db, _ = _db_with_doc("entitlement_cache", "user-1", None)
        assert gate_service.get_limits(db, "user-1") is None

    def test_get_limits_returns_dict_when_row_exists(self):
        db, _ = _db_with_doc(
            "entitlement_cache",
            "user-1",
            {"max_workspaces": 10, "max_artifacts": 500, "vu_limit": 1000},
        )
        out = gate_service.get_limits(db, "user-1")
        assert out == {
            "max_workspaces": 10,
            "max_artifacts": 500,
            "vu_limit": 1000,
        }

    def test_get_or_default_falls_back_to_free_tier(self):
        db, _ = _db_with_doc("entitlement_cache", "user-1", None)
        out = gate_service.get_or_default_limits(db, "user-1")
        # Free tier defaults from the module constant.
        assert out["max_workspaces"] == 1
        assert out["vu_limit"] == 100

    def test_set_limits_inserts_when_missing(self):
        db, coll = _db_with_doc("entitlement_cache", "user-1", None)
        gate_service.set_limits(db, "user-1", max_workspaces=10, vu_limit=500)
        coll.insert.assert_called_once()
        coll.update.assert_not_called()
        doc = coll.insert.call_args[0][0]
        assert doc["_key"] == "user-1"
        assert doc["max_workspaces"] == 10
        assert doc["vu_limit"] == 500

    def test_set_limits_updates_when_present(self):
        db, coll = _db_with_doc(
            "entitlement_cache", "user-1", {"max_workspaces": 1}
        )
        gate_service.set_limits(db, "user-1", max_workspaces=99)
        coll.update.assert_called_once()
        coll.insert.assert_not_called()


# ---------------------------------------------------------------------------
# Tallies
# ---------------------------------------------------------------------------

class TestTallies:
    def test_get_tally_zero_when_no_row(self):
        db, _ = _db_with_doc("usage_tallies", "user-1:vu:2026-04", None)
        assert gate_service.get_tally(db, "user-1", "vu", "2026-04") == 0

    def test_get_tally_returns_total(self):
        db, _ = _db_with_doc(
            "usage_tallies", "user-1:vu:2026-04", {"total": 42}
        )
        assert gate_service.get_tally(db, "user-1", "vu", "2026-04") == 42

    def test_add_tally_inserts_when_missing(self):
        db, coll = _db_with_doc("usage_tallies", "user-1:vu:2026-04", None)
        result = gate_service.add_tally(db, "user-1", "vu", "2026-04", amount=5)
        assert result == 5
        coll.insert.assert_called_once()
        doc = coll.insert.call_args[0][0]
        assert doc["_key"] == "user-1:vu:2026-04"
        assert doc["total"] == 5
        assert doc["dimension"] == "vu"
        assert doc["period"] == "2026-04"

    def test_add_tally_updates_via_aql_when_present(self):
        db, coll = _db_with_doc(
            "usage_tallies", "user-1:vu:2026-04", {"total": 5}
        )
        # AQL execute returns iterator yielding the new doc.
        db.aql.execute.return_value = iter([{"total": 12}])
        result = gate_service.add_tally(db, "user-1", "vu", "2026-04", amount=7)
        assert result == 12
        db.aql.execute.assert_called_once()

    def test_get_all_tallies_groups_by_dimension(self):
        db = MagicMock()
        db.aql.execute.return_value = iter([
            {"dimension": "vu", "period": "2026-04", "total": 100},
            {"dimension": "vu", "period": "2026-03", "total": 250},
            {"dimension": "tokens", "period": "2026-04", "total": 5000},
        ])
        out = gate_service.get_all_tallies(db, "user-1")
        assert out == {
            "vu": {"2026-04": 100, "2026-03": 250},
            "tokens": {"2026-04": 5000},
        }


# ---------------------------------------------------------------------------
# Live counts (post-fix: unified store collection names)
# ---------------------------------------------------------------------------

class TestLiveCounts:
    def test_count_workspaces_queries_collections_table_with_workspace_content_type(self):
        """Regression: pre-fix this queried the deleted `workspaces` collection.
        Now it queries `collections` filtered by content_type=workspace."""
        db = MagicMock()
        db.aql.execute.return_value = iter([7])
        out = gate_service.count_workspaces(db, "user-1")
        assert out == 7

        # Verify the AQL query uses the unified `artifacts` collection and
        # filters by the workspace content_type.
        call = db.aql.execute.call_args
        aql = call.args[0] if call.args else call.kwargs.get("query", "")
        assert "FOR c IN artifacts" in aql
        assert "created_by" in aql
        # Bind vars carry the workspace content_type constant.
        bind_vars = call.kwargs.get("bind_vars", {})
        assert bind_vars.get("ws_content_type") == WORKSPACE_CONTENT_TYPE
        assert bind_vars.get("pid") == "user-1"

    def test_count_workspaces_zero_when_empty(self):
        db = MagicMock()
        db.aql.execute.return_value = iter([])
        assert gate_service.count_workspaces(db, "user-1") == 0

    def test_count_artifacts_queries_unified_artifacts_table(self):
        db = MagicMock()
        db.aql.execute.return_value = iter([42])
        out = gate_service.count_artifacts(db, "user-1")
        assert out == 42
        aql = db.aql.execute.call_args.args[0]
        assert "FOR a IN artifacts" in aql
        assert "workspace_artifacts" not in aql

    def test_count_artifacts_excludes_archived(self):
        db = MagicMock()
        db.aql.execute.return_value = iter([5])
        gate_service.count_artifacts(db, "user-1")
        aql = db.aql.execute.call_args.args[0]
        assert "archived" in aql

    def test_count_artifacts_zero_when_empty(self):
        db = MagicMock()
        db.aql.execute.return_value = iter([])
        assert gate_service.count_artifacts(db, "user-1") == 0
