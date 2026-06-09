"""HTTP tests for `origin.routers.auth_router`.

Covers the most security-critical paths:

- `/auth/password/login` — credential check, dummy-verify on missing user
  (timing-safe), 401 on bad password, token shape on success.
- `/auth/password/register` — gate, validation, token issuance.
- `/auth/token` (client_credentials) — kernel fast-path with
  PLATFORM_INTERNAL_SECRET, bad secret → 401, unknown client → 401.
- `/auth/token` (refresh_token) — missing field → 400.
- `/auth/userinfo` + `/me/preferences` — auth required, returns user
  data + roles, preferences round-trip.
- `/auth/nonce` — only accepts inbound API keys configured for nonce.
- `/auth/providers` — provider listing.

OAuth `/authorize` and `/callback` are end-to-end browser redirects that
need extensive OIDC stubbing — out of scope for this fast unit suite.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from origin.routers.auth_router import auth_router, internal_router, root_router
from origin.services.dependencies import AuthContext, get_auth, get_person
from origin.db.session import get_db


def _make_app(auth: AuthContext, *, person: object | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(root_router)
    app.include_router(internal_router)

    def _override_auth() -> AuthContext:
        return auth

    def _override_person():
        if person is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="User identification required")
        return person

    def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_auth] = _override_auth
    app.dependency_overrides[get_person] = _override_person
    app.dependency_overrides[get_db] = _override_db
    return app


def _person(**overrides):
    base = dict(
        id=uuid.uuid4(),
        username="alice",
        email="alice@example.com",
        name="Alice",
        picture=None,
        password_hash="$2b$12$abcdefghijklmnopqrstuv",
        preferences={},
        google_id=None,
        oidc_provider=None,
        oidc_subject=None,
        created_time=None,
        modified_time=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Password login
# ---------------------------------------------------------------------------

class TestPasswordLogin:
    @pytest.fixture
    def anon_client(self):
        return TestClient(_make_app(AuthContext()))

    def test_disabled_returns_404(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=False,
        ):
            resp = anon_client.post(
                "/auth/password/login",
                json={"identifier": "alice", "password": "x"},
            )
        assert resp.status_code == 404

    def test_missing_fields_400(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ):
            resp = anon_client.post(
                "/auth/password/login",
                json={"identifier": "", "password": ""},
            )
        assert resp.status_code == 400

    def test_unknown_user_runs_dummy_verify_and_401s(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.person_service.get_user_by_username",
            return_value=None,
        ), patch(
            "origin.routers.auth_router.dummy_verify_password",
        ) as dummy:
            resp = anon_client.post(
                "/auth/password/login",
                json={"identifier": "ghost", "password": "x"},
            )
        # Constant-time check still runs even though user is missing.
        dummy.assert_called_once_with("x")
        assert resp.status_code == 401

    def test_bad_password_401(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.person_service.get_user_by_username",
            return_value=_person(),
        ), patch(
            "origin.routers.auth_router.verify_password",
            return_value=False,
        ):
            resp = anon_client.post(
                "/auth/password/login",
                json={"identifier": "alice", "password": "wrong"},
            )
        assert resp.status_code == 401

    def test_email_identifier_routes_to_email_lookup(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.person_service.get_user_by_email",
            return_value=_person(),
        ) as by_email, patch(
            "origin.routers.auth_router.person_service.get_user_by_username"
        ) as by_username, patch(
            "origin.routers.auth_router.verify_password",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.create_jwt_token",
            return_value="mock.jwt.token",
        ), patch(
            "origin.routers.auth_router._compute_roles",
            return_value=[],
        ):
            resp = anon_client.post(
                "/auth/password/login",
                json={"identifier": "ALICE@EXAMPLE.COM", "password": "ok"},
            )
        assert resp.status_code == 200
        # Email lookup ran with lowercased email; username lookup didn't fire.
        by_email.assert_called_once_with(by_email.call_args.args[0], "alice@example.com")
        by_username.assert_not_called()

    def test_success_returns_access_and_refresh_tokens(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.person_service.get_user_by_username",
            return_value=_person(),
        ), patch(
            "origin.routers.auth_router.verify_password",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.create_jwt_token",
            side_effect=["access.jwt", "refresh.jwt"],
        ), patch(
            "origin.routers.auth_router._compute_roles",
            return_value=["operator"],
        ):
            resp = anon_client.post(
                "/auth/password/login",
                json={"identifier": "alice", "password": "ok"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"] == "access.jwt"
        assert body["refresh_token"] == "refresh.jwt"
        assert body["expires_in"] == 3600 * 12


# ---------------------------------------------------------------------------
# Password register
# ---------------------------------------------------------------------------

class TestPasswordRegister:
    @pytest.fixture
    def anon_client(self):
        return TestClient(_make_app(AuthContext()))

    def test_disabled_returns_404(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=False,
        ):
            resp = anon_client.post(
                "/auth/password/register",
                json={"username": "alice", "password": "p" * 12},
            )
        assert resp.status_code == 404

    def test_username_required(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ):
            resp = anon_client.post(
                "/auth/password/register",
                json={"username": "", "password": "p" * 12},
            )
        assert resp.status_code == 400

    def test_short_password_400(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.platform_settings.get_int",
            return_value=12,
        ):
            resp = anon_client.post(
                "/auth/password/register",
                json={"username": "alice", "password": "short"},
            )
        assert resp.status_code == 400
        assert "12 characters" in resp.json()["detail"]

    def test_invalid_email_400(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.platform_settings.get_int",
            return_value=12,
        ):
            resp = anon_client.post(
                "/auth/password/register",
                json={"username": "alice", "password": "p" * 12, "email": "noatsign"},
            )
        assert resp.status_code == 400

    def test_invite_only_blocks_registration(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.platform_settings.get_int",
            return_value=12,
        ), patch(
            "origin.routers.auth_router.hash_password",
            return_value="HASH",
        ), patch(
            "origin.routers.auth_router.person_service.create_user_with_password",
            side_effect=PermissionError("Registration is invite-only"),
        ):
            resp = anon_client.post(
                "/auth/password/register",
                json={"username": "alice", "password": "p" * 12},
            )
        assert resp.status_code == 403

    def test_value_error_collapses_to_400_without_leak(self, anon_client):
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.platform_settings.get_int",
            return_value=12,
        ), patch(
            "origin.routers.auth_router.hash_password",
            return_value="HASH",
        ), patch(
            "origin.routers.auth_router.person_service.create_user_with_password",
            side_effect=ValueError("Username already taken"),
        ):
            resp = anon_client.post(
                "/auth/password/register",
                json={"username": "alice", "password": "p" * 12},
            )
        assert resp.status_code == 400
        # Generic message — never leak whether the username/email exists.
        assert resp.json()["detail"] == "Registration failed"

    def test_success_returns_tokens(self, anon_client):
        person = _person()
        with patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ), patch(
            "origin.routers.auth_router.platform_settings.get_int",
            return_value=12,
        ), patch(
            "origin.routers.auth_router.hash_password",
            return_value="HASH",
        ), patch(
            "origin.routers.auth_router.person_service.create_user_with_password",
            return_value=person,
        ), patch(
            "origin.routers.auth_router.create_jwt_token",
            side_effect=["access.jwt", "refresh.jwt"],
        ), patch(
            "origin.routers.auth_router._compute_roles",
            return_value=[],
        ):
            resp = anon_client.post(
                "/auth/password/register",
                json={"username": "alice", "password": "p" * 12, "email": "a@b.co"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.jwt"
        assert body["refresh_token"] == "refresh.jwt"


# ---------------------------------------------------------------------------
# /auth/token — client_credentials (kernel fast-path)
# ---------------------------------------------------------------------------

class TestTokenClientCredentials:
    @pytest.fixture
    def anon_client(self):
        return TestClient(_make_app(AuthContext()))

    def test_missing_fields_400(self, anon_client):
        resp = anon_client.post(
            "/auth/token",
            data={"grant_type": "client_credentials"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "invalid_request"

    def test_unknown_client_returns_401(self, anon_client):
        # Phase C: kernel fast-path is removed. Unknown clients fall through
        # to the standard DB-backed OAuth client check, which returns 401.
        with patch(
            "origin.routers.auth_router.db_server_credentials.get_by_client_id",
            return_value=None,
        ):
            resp = anon_client.post(
                "/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": "unknown",
                    "client_secret": "x",
                },
            )
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_client"

    # Phase C removes the kernel-server fast-path entirely. Kernel callers
    # (Mantle, Chorus) sign their own JWTs with `mantle.private.pem` /
    # `chorus.private.pem` and don't ask Origin for tokens, so there are no
    # `client_credentials` exchanges with `PLATFORM_INTERNAL_SECRET` to test.
    # Tests exercising mutual JWT verification live in
    # mantle/tests/test_authority_trust.py and mantle/tests/test_service_identity.py.

    def test_unsupported_grant_type_400(self, anon_client):
        resp = anon_client.post(
            "/auth/token",
            data={"grant_type": "magic", "client_id": "x", "client_secret": "y"},
        )
        assert resp.status_code == 400

    def test_refresh_token_missing_field_400(self, anon_client):
        resp = anon_client.post(
            "/auth/token",
            data={"grant_type": "refresh_token"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /userinfo + /me/preferences
# ---------------------------------------------------------------------------

class TestUserInfo:
    def test_userinfo_requires_auth(self):
        client = TestClient(_make_app(AuthContext()))
        resp = client.get("/auth/userinfo")
        assert resp.status_code == 401

    def test_userinfo_returns_user_payload(self):
        person = _person()
        auth = AuthContext(principal_id=str(person.id), principal_type="user", user_id=str(person.id))
        client = TestClient(_make_app(auth, person=person))
        with patch("origin.routers.auth_router._compute_roles", return_value=["operator"]):
            resp = client.get("/auth/userinfo")
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "alice@example.com"
        assert body["roles"] == ["operator"]
        assert "platform_user_id" in body


class TestPreferences:
    def test_get_returns_existing_prefs(self):
        person = _person(preferences={"theme": "dark"})
        auth = AuthContext(principal_id=str(person.id), principal_type="user", user_id=str(person.id))
        client = TestClient(_make_app(auth, person=person))
        resp = client.get("/auth/me/preferences")
        assert resp.status_code == 200
        assert resp.json() == {"theme": "dark"}

    def test_get_handles_null_prefs(self):
        person = _person(preferences=None)
        auth = AuthContext(principal_id=str(person.id), principal_type="user", user_id=str(person.id))
        client = TestClient(_make_app(auth, person=person))
        resp = client.get("/auth/me/preferences")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_patch_round_trips(self):
        person = _person(preferences={"theme": "dark"})
        updated = _person(preferences={"theme": "light", "lang": "en"})
        auth = AuthContext(principal_id=str(person.id), principal_type="user", user_id=str(person.id))
        client = TestClient(_make_app(auth, person=person))
        with patch(
            "origin.routers.auth_router.person_service.update_preferences",
            return_value=updated,
        ):
            resp = client.patch(
                "/auth/me/preferences",
                json={"theme": "light", "lang": "en"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"theme": "light", "lang": "en"}


# ---------------------------------------------------------------------------
# /nonce — inbound API keys only
# ---------------------------------------------------------------------------

class TestNonce:
    def test_user_principal_403(self):
        auth = AuthContext(principal_id="user-1", principal_type="user", user_id="user-1")
        client = TestClient(_make_app(auth))
        resp = client.get("/auth/nonce")
        assert resp.status_code == 403

    def test_api_key_without_requires_nonce_403(self):
        ak = SimpleNamespace(requires_nonce=False)
        auth = AuthContext(
            principal_id="ak-1",
            principal_type="api_key",
            api_key_id="ak-1",
            api_key_entity=ak,
        )
        client = TestClient(_make_app(auth))
        resp = client.get("/auth/nonce")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /providers
# ---------------------------------------------------------------------------

class TestProviders:
    def test_returns_registered_providers(self):
        client = TestClient(_make_app(AuthContext()))
        with patch.dict(
            "origin.routers.auth_router.REGISTERED_PROVIDERS",
            {"google": {"label": "Google"}, "microsoft": {"label": "Microsoft"}},
            clear=True,
        ), patch(
            "origin.routers.auth_router.platform_settings.get_bool",
            return_value=True,
        ):
            resp = client.get("/auth/providers")
        assert resp.status_code == 200
        body = resp.json()
        assert {p["name"] for p in body["providers"]} == {"google", "microsoft"}
        assert body["password"] is True
        assert "otp" in body
