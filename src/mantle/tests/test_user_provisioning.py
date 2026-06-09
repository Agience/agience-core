"""Per-user provisioning: the declarative `package/seeds/user` grant artifacts
applied through `provision_user`, with the inbox-workspace + materialization glue
stubbed (they loop over live DB state and are covered by their own paths).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SEEDS_BASE = Path(__file__).resolve().parents[3] / "package" / "seeds"

# Platform collections a first-login user is granted on.
_USER_GRANT_SLUGS = [
    "agience-authorities", "agience-hosts", "agience-resources",
    "agience-llm-connections", "agience-inbox-seeds", "agience-seeds-start-here",
    "agience-seeds-platform-artifacts", "agience-seeds-all-tools",
    "agience-seeds-agents", "agience-package-registry", "agience-seeds-all-servers",
]


@pytest.fixture(autouse=True)
def _registry(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    from services import platform_topology

    platform_topology.clear_registry()
    for slug in _USER_GRANT_SLUGS:
        platform_topology.register_id(slug, f"id-{slug}")
    yield
    platform_topology.clear_registry()


def _provision(is_admin: bool = False):
    captured: list[dict] = []
    with (
        patch("services.seed_provisioning.loader.db_upsert_user_collection_grant",
              side_effect=lambda db, **kw: (captured.append(kw), (MagicMock(), True))[1]),
        patch("services.seed_provisioning.user_provisioning._ensure_inbox_workspace",
              return_value="ws-1") as mock_ws,
        patch("services.seed_provisioning.user_provisioning._materialize_inbox") as mock_mat,
        patch("services.seed_provisioning.user_provisioning._is_platform_admin",
              return_value=is_admin),
    ):
        from services.seed_provisioning import user_provisioning
        user_provisioning.provision_user(MagicMock(), "user-9", seeds_base=SEEDS_BASE)
    return captured, mock_ws, mock_mat


def test_provision_user_issues_read_grants():
    grants, _, _ = _provision(is_admin=False)
    assert len(grants) == len(_USER_GRANT_SLUGS) == 11
    assert all(g["user_id"] == "user-9" for g in grants)
    by_res = {g["collection_id"]: g for g in grants}
    # Read-only on the registry collections; no admin for a normal user.
    auth = by_res["id-agience-authorities"]
    assert auth["can_read"] and not auth["can_update"] and not auth["can_admin"]
    # Servers get read + invoke.
    servers = by_res["id-agience-seeds-all-servers"]
    assert servers["can_read"] and servers["can_invoke"] and not servers["can_update"]


def test_provision_designated_admin_adds_full_grants():
    """The designated platform admin gets the admin grant set (full) on every
    platform collection, on top of the base user reads — same grant format, just
    a fuller set. The admin grants are applied last, so they win."""
    grants, _, _ = _provision(is_admin=True)
    # 11 user reads + 11 admin grants.
    assert len(grants) == 22
    by_res_last = {g["collection_id"]: g for g in grants}  # admin set applied last
    for slug in _USER_GRANT_SLUGS:
        g = by_res_last[f"id-{slug}"]
        assert g["can_read"] and g["can_update"] and g["can_invoke"] and g["can_admin"], slug


def test_provision_user_runs_inbox_glue():
    _, mock_ws, mock_mat = _provision()
    mock_ws.assert_called_once()
    mock_mat.assert_called_once()


def test_provision_user_empty_user_id_is_noop():
    with patch("services.seed_provisioning.user_provisioning._ensure_inbox_workspace") as mock_ws:
        from services.seed_provisioning import user_provisioning
        user_provisioning.provision_user(MagicMock(), "")
    mock_ws.assert_not_called()
