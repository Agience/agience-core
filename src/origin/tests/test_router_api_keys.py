"""HTTP tests for `origin.routers.api_keys_router`.

Coverage:
- Create: requires user JWT (rejected for api_key/server principals);
  returns the raw key exactly once on creation; default scopes/filters
  applied when payload omits them.
- List/get: scoped to the calling user; cross-user reads return 404.
- Update/delete: also user-JWT-only; cross-user 404.
- Internal `/verify`: kernel-server-only; returns metadata + grants;
  invalid token → 404.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from origin.routers.api_keys_router import (
    internal_router as api_keys_internal_router,
    router as api_keys_router,
)
from origin.services.dependencies import AuthContext, get_auth
from origin.db.session import get_db


def _make_app(auth: AuthContext) -> FastAPI:
    app = FastAPI()
    app.include_router(api_keys_internal_router)
    app.include_router(api_keys_router)

    def _override_auth() -> AuthContext:
        return auth

    def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_auth] = _override_auth
    app.dependency_overrides[get_db] = _override_db
    return app


def _api_key(**overrides):
    base = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        key_hash="hashedvalue",
        name="My Key",
        client_id="cl-1",
        host_id=None,
        server_id=None,
        agent_id=None,
        display_label="Easy MCP Key",
        issued_by_user_id=uuid.uuid4(),
        created_from_client_id="cl-1",
        scopes=["resource:*:read"],
        resource_filters={"workspaces": "*"},
        created_time=datetime.now(timezone.utc),
        modified_time=None,
        expires_at=None,
        last_used_at=None,
        is_active=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _grant(**overrides):
    base = dict(
        id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        grantee_type="api_key",
        grantee_id="api-1",
        effect="allow",
        can_create=False,
        can_read=True,
        can_update=False,
        can_delete=False,
        can_evict=False,
        can_invoke=False,
        can_add=False,
        can_share=False,
        can_admin=False,
        state="active",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def user_client():
    auth = AuthContext(principal_id="user-1", principal_type="user", user_id="user-1")
    return TestClient(_make_app(auth))


@pytest.fixture
def api_key_client():
    auth = AuthContext(
        principal_id="ak-1", principal_type="api_key", user_id="user-1", api_key_id="ak-1"
    )
    return TestClient(_make_app(auth))


@pytest.fixture
def server_client():
    auth = AuthContext(principal_id="agience-mantle", principal_type="server")
    return TestClient(_make_app(auth))


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestCreate:
    def test_user_jwt_creates_and_returns_raw_key_once(self, user_client):
        ak = _api_key(name="MyKey")
        with patch(
            "origin.routers.api_keys_router.auth_svc.generate_api_key",
            return_value="agc_RAW",
        ), patch(
            "origin.routers.api_keys_router.auth_svc.hash_api_key",
            return_value="HASH",
        ), patch(
            "origin.routers.api_keys_router.db_api_keys.create",
            return_value=ak,
        ) as create:
            resp = user_client.post("/auth/keys", json={"name": "MyKey"})

        assert resp.status_code == 201
        body = resp.json()
        assert body["key"] == "agc_RAW"  # raw token, returned once
        assert body["name"] == "MyKey"
        # Default scopes + filters applied
        fields = create.call_args.args[1]
        assert "resource:*:read" in fields["scopes"]
        assert fields["resource_filters"] == {"workspaces": "*", "collections": "*"}
        # Hashed value persisted, raw key never stored
        assert fields["key_hash"] == "HASH"

    def test_api_key_principal_cannot_create(self, api_key_client):
        # API keys cannot mint other API keys.
        resp = api_key_client.post("/auth/keys", json={"name": "Nope"})
        assert resp.status_code == 403

    def test_server_principal_cannot_create(self, server_client):
        resp = server_client.post("/auth/keys", json={"name": "Nope"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Read paths
# ---------------------------------------------------------------------------

class TestList:
    def test_lists_caller_keys(self, user_client):
        keys = [_api_key(name="a"), _api_key(name="b")]
        with patch(
            "origin.routers.api_keys_router.db_api_keys.get_by_user",
            return_value=keys,
        ):
            resp = user_client.get("/auth/keys")
        assert resp.status_code == 200
        assert {k["name"] for k in resp.json()} == {"a", "b"}


class TestGet:
    def test_returns_only_own_key(self, user_client):
        ak = _api_key(user_id="user-1")
        with patch(
            "origin.routers.api_keys_router.db_api_keys.get_by_id",
            return_value=ak,
        ):
            resp = user_client.get(f"/auth/keys/{ak.id}")
        assert resp.status_code == 200

    def test_other_users_key_404(self, user_client):
        ak = _api_key(user_id="user-2")
        with patch(
            "origin.routers.api_keys_router.db_api_keys.get_by_id",
            return_value=ak,
        ):
            resp = user_client.get(f"/auth/keys/{ak.id}")
        assert resp.status_code == 404

    def test_missing_404(self, user_client):
        with patch(
            "origin.routers.api_keys_router.db_api_keys.get_by_id",
            return_value=None,
        ):
            resp = user_client.get(f"/auth/keys/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update / delete
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_user_can_update_own(self, user_client):
        ak = _api_key(user_id="user-1", name="old")
        updated = _api_key(user_id="user-1", name="new")
        with patch(
            "origin.routers.api_keys_router.db_api_keys.get_by_id",
            return_value=ak,
        ), patch(
            "origin.routers.api_keys_router.db_api_keys.update",
            return_value=updated,
        ):
            resp = user_client.patch(f"/auth/keys/{ak.id}", json={"name": "new"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "new"

    def test_api_key_principal_cannot_update(self, api_key_client):
        ak = _api_key()
        # Hits the user-JWT guard before ever touching the DB.
        resp = api_key_client.patch(f"/auth/keys/{ak.id}", json={"name": "x"})
        assert resp.status_code == 403

    def test_other_users_key_404(self, user_client):
        ak = _api_key(user_id="user-2")
        with patch(
            "origin.routers.api_keys_router.db_api_keys.get_by_id",
            return_value=ak,
        ):
            resp = user_client.patch(f"/auth/keys/{ak.id}", json={"name": "x"})
        assert resp.status_code == 404


class TestDelete:
    def test_user_can_delete_own(self, user_client):
        ak = _api_key(user_id="user-1")
        with patch(
            "origin.routers.api_keys_router.db_api_keys.get_by_id",
            return_value=ak,
        ), patch(
            "origin.routers.api_keys_router.db_api_keys.delete",
            return_value=True,
        ):
            resp = user_client.delete(f"/auth/keys/{ak.id}")
        assert resp.status_code == 204

    def test_api_key_principal_cannot_delete(self, api_key_client):
        resp = api_key_client.delete(f"/auth/keys/{uuid.uuid4()}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Internal /verify
# ---------------------------------------------------------------------------

class TestInternalVerify:
    def test_user_principal_403(self, user_client):
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle"],
        ):
            resp = user_client.post("/auth/keys/verify", json={"token": "agc_x"})
        assert resp.status_code == 403

    def test_kernel_server_unknown_token_404(self, server_client):
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle"],
        ), patch(
            "origin.services.auth_verifier.verify_api_key",
            return_value=None,
        ):
            resp = server_client.post("/auth/keys/verify", json={"token": "agc_x"})
        assert resp.status_code == 404

    def test_kernel_server_returns_metadata_and_grants(self, server_client):
        ak = _api_key()
        grants = [_grant(can_read=True), _grant(can_invoke=True, state="revoked")]
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle"],
        ), patch(
            "origin.services.auth_verifier.verify_api_key",
            return_value=ak,
        ), patch(
            "origin.db.grants.get_active_for_grantee",
            return_value=grants,
        ):
            resp = server_client.post("/auth/keys/verify", json={"token": "agc_x"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["api_key"]["id"] == str(ak.id)
        # Both grants pass through; the router doesn't filter state — Mantle does.
        assert len(body["grants"]) == 2
        assert any(g["can_read"] for g in body["grants"])
