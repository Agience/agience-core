"""Tests for the merged platform_router.

Covers the seven endpoints merged from the retired operator_router and
admin_router (2026-04-06). Grant checks are mocked at the
`routers.platform_router.require_platform_admin` boundary, so the tests
focus on router behavior + service dispatch, not on the grant system
itself (which is covered by its own test suite).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_platform_admin():
    """Patch require_platform_admin to return a fixed user ID (auth passes)."""
    with patch("routers.platform_router.require_platform_admin", return_value="user-123"):
        yield


@pytest.fixture
def deny_platform_admin():
    """Patch require_platform_admin to raise 403."""
    def _deny(*args, **kwargs):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Platform admin access required")
    with patch("routers.platform_router.require_platform_admin", side_effect=_deny):
        yield


@pytest.fixture
def client():
    from main import app
    from core.dependencies import get_arango_db
    from services.dependencies import get_auth, AuthContext
    app.dependency_overrides[get_auth] = lambda: AuthContext(
        principal_id="user-123", principal_type="user", user_id="user-123"
    )
    app.dependency_overrides[get_arango_db] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------

class TestPlatformSettings:

    @patch("routers.platform_router.platform_settings")
    def test_get_all_settings(self, mock_settings, mock_platform_admin, client):
        mock_settings.get_all_by_category.return_value = {
            "auth": [{"key": "auth.allowed_emails", "value": "a@b.com", "is_secret": False}],
            "branding": [{"key": "branding.title", "value": "Agience", "is_secret": False}],
        }

        resp = client.get("/platform/settings")

        assert resp.status_code == 200
        body = resp.json()
        assert "categories" in body
        assert "auth" in body["categories"]
        assert "branding" in body["categories"]
        mock_settings.get_all_by_category.assert_called_once_with()

    @patch("routers.platform_router.platform_settings")
    def test_get_settings_by_category(self, mock_settings, mock_platform_admin, client):
        mock_settings.get_all_by_category.return_value = {
            "auth": [{"key": "auth.allowed_emails", "value": "a@b.com", "is_secret": False}],
        }

        resp = client.get("/platform/settings/auth")

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["key"] == "auth.allowed_emails"
        mock_settings.get_all_by_category.assert_called_once_with(category="auth")

    @patch("core.config.load_settings_from_db")
    @patch("routers.platform_router.platform_settings")
    def test_update_settings_patches_and_reloads_config(
        self, mock_settings, mock_load_config, mock_platform_admin, client
    ):
        mock_settings.set_many.return_value = 2

        resp = client.patch("/platform/settings", json={
            "settings": [
                {"key": "branding.title", "value": "New Title", "is_secret": False},
                {"key": "auth.allowed_emails", "value": "x@y.com", "is_secret": False},
            ],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] == 2
        assert body["restart_required"] is False
        mock_settings.set_many.assert_called_once()
        mock_load_config.assert_called_once()

    @patch("core.config.load_settings_from_db")
    @patch("routers.platform_router.platform_settings")
    def test_update_settings_flags_restart_for_infrastructure_keys(
        self, mock_settings, mock_load_config, mock_platform_admin, client
    ):
        mock_settings.set_many.return_value = 1

        resp = client.patch("/platform/settings", json={
            "settings": [{"key": "db.arango.host", "value": "new-host", "is_secret": False}],
        })

        assert resp.status_code == 200
        assert resp.json()["restart_required"] is True

    @patch("core.config.load_settings_from_db")
    @patch("routers.platform_router.platform_settings")
    def test_update_settings_skips_null_secret_values(
        self, mock_settings, mock_load_config, mock_platform_admin, client
    ):
        """Masked secret values (null from GET) must not overwrite stored secrets."""
        mock_settings.set_many.return_value = 0

        resp = client.patch("/platform/settings", json={
            "settings": [
                {"key": "ai.openai_api_key", "value": None, "is_secret": True},
                {"key": "auth.google.client_secret", "value": "", "is_secret": True},
            ],
        })

        assert resp.status_code == 200
        # set_many should be called with an empty list (both items skipped)
        call_args = mock_settings.set_many.call_args
        assert call_args.args[1] == []

    def test_settings_endpoints_deny_non_admin(self, deny_platform_admin, client):
        assert client.get("/platform/settings").status_code == 403
        assert client.get("/platform/settings/auth").status_code == 403
        assert client.patch("/platform/settings", json={"settings": []}).status_code == 403


# ---------------------------------------------------------------------------
# User admin endpoints
# ---------------------------------------------------------------------------

class TestPlatformUsers:

    @patch("routers.platform_router._is_user_platform_admin", return_value=True)
    @patch("routers.platform_router.db_list_all_people")
    def test_list_users(self, mock_list_people, _mock_is_admin, mock_platform_admin, client):
        mock_list_people.return_value = [
            {
                "_key": "user-1", "email": "a@b.com", "name": "Alice",
                "picture": None, "created_time": "2026-01-01T00:00:00Z",
            },
            {
                "_key": "user-2", "email": "b@c.com", "name": "Bob",
                "picture": None, "created_time": "2026-02-01T00:00:00Z",
            },
        ]

        resp = client.get("/platform/users")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["users"]) == 2
        assert body["users"][0]["id"] == "user-1"
        assert body["users"][0]["is_platform_admin"] is True

    @patch("routers.platform_router.db_upsert_grant")
    @patch("routers.platform_router.get_all_platform_collection_ids", return_value=["col-1", "col-2"])
    @patch("routers.platform_router.db_get_person_by_id")
    def test_grant_platform_admin(
        self, mock_get_person, mock_col_ids, mock_upsert, mock_platform_admin, client
    ):
        mock_get_person.return_value = {"_key": "user-456", "email": "new@admin.com"}

        resp = client.post("/platform/users/user-456/grant-admin")

        assert resp.status_code == 200
        assert resp.json() == {"status": "granted", "user_id": "user-456"}
        # upsert called once per platform collection
        assert mock_upsert.call_count == 2

    @patch("routers.platform_router.db_get_person_by_id", return_value=None)
    def test_grant_platform_admin_user_not_found(
        self, _mock_get_person, mock_platform_admin, client
    ):
        resp = client.post("/platform/users/ghost/grant-admin")
        assert resp.status_code == 404

    @patch("routers.platform_router.db_upsert_grant")
    @patch("routers.platform_router.get_all_platform_collection_ids", return_value=["col-1"])
    @patch("routers.platform_router.db_get_person_by_id")
    def test_revoke_platform_admin(
        self, mock_get_person, mock_col_ids, mock_upsert, mock_platform_admin, client
    ):
        mock_get_person.return_value = {"_key": "user-456"}

        resp = client.delete("/platform/users/user-456/revoke-admin")

        assert resp.status_code == 200
        assert resp.json() == {"status": "revoked", "user_id": "user-456"}

    def test_cannot_revoke_own_platform_admin(self, mock_platform_admin, client):
        # mock_platform_admin fixture returns "user-123" as the authed admin
        resp = client.delete("/platform/users/user-123/revoke-admin")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Seed collections endpoint
# ---------------------------------------------------------------------------

class TestPlatformSeedCollections:

    @patch("routers.platform_router.db_list_collection_artifacts", return_value=[{"id": "a1"}, {"id": "a2"}])
    @patch("routers.platform_router.db_get_collection_by_id")
    @patch("routers.platform_router.get_all_platform_collection_ids", return_value=["col-1"])
    def test_list_seed_collections(
        self, _mock_ids, mock_get_col, _mock_get_arts, mock_platform_admin, client
    ):
        fake_col = MagicMock()
        fake_col.id = "col-1"
        fake_col.name = "Authorities"
        fake_col.description = "Platform authority records"
        mock_get_col.return_value = fake_col

        resp = client.get("/platform/seed-collections")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == "col-1"
        assert body[0]["artifact_count"] == 2
