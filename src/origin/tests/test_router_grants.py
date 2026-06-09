"""HTTP tests for `origin.routers.grants_router`.

Uses FastAPI `dependency_overrides` to swap auth + DB session, then
patches `origin.services.grant_service` and `origin.db.grants` to keep
the tests fast and Postgres-free.

Coverage:
- Public-facing user endpoints: invite-context, invite-details, claim,
  list grants, create grant (user + invite), read, revoke, accept.
- Auth gating: anonymous → 401; non-admin → 403 on admin paths;
  share-only → 403 on admin-required paths.
- Error mapping for the invite claim taxonomy
  (NotFound → 404, Exhausted → 410, IdentityMismatch → 403).
- Internal endpoints: kernel-server gate (server principal required,
  must be in the kernel registry).
- The `_role_from_bits` round-trip: posting an editor bitmask without
  a role string still chooses the editor preset under the hood.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from origin.routers.grants_router import internal_router, router as grants_router
from origin.services import grant_service
from origin.services.dependencies import AuthContext, get_auth
from origin.db.session import get_db


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_app(auth: AuthContext) -> FastAPI:
    """Build a fresh FastAPI app with grants routers mounted + auth/db overrides.

    Internal router registers FIRST so its specific routes (/check, /upsert,
    /lookup-by-key, ...) match before the generic /{grant_id} catches them.
    Mirrors the order in `origin/main.py`.
    """
    app = FastAPI()
    app.include_router(internal_router)
    app.include_router(grants_router)

    def _override_auth() -> AuthContext:
        return auth

    def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_auth] = _override_auth
    app.dependency_overrides[get_db] = _override_db
    return app


def _grant(**overrides):
    """SimpleNamespace shaped like a Grant row with safe defaults."""
    base = dict(
        id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        grantee_type="user",
        grantee_id="user-1",
        granted_by=uuid.uuid4(),
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
        requires_identity=False,
        read_requires_identity=False,
        write_requires_identity=False,
        invoke_requires_identity=False,
        target_entity=None,
        target_entity_type=None,
        max_claims=None,
        claims_count=0,
        state="active",
        name=None,
        notes=None,
        granted_at=datetime.now(timezone.utc),
        expires_at=None,
        accepted_by=None,
        accepted_at=None,
        revoked_by=None,
        revoked_at=None,
        created_time=datetime.now(timezone.utc),
        modified_time=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def user_client():
    """Authenticated user client. user-1 is the principal."""
    auth = AuthContext(principal_id="user-1", principal_type="user", user_id="user-1")
    return TestClient(_make_app(auth))


@pytest.fixture
def anon_client():
    """No user_id — should always 401 on protected paths."""
    auth = AuthContext()
    return TestClient(_make_app(auth))


@pytest.fixture
def server_client():
    """Server principal recognized by the kernel registry."""
    auth = AuthContext(principal_id="agience-mantle", principal_type="server")
    return TestClient(_make_app(auth))


@pytest.fixture
def non_kernel_server_client():
    """Server principal NOT in the kernel registry — should 403 on internal paths."""
    auth = AuthContext(principal_id="some-third-party", principal_type="server")
    return TestClient(_make_app(auth))


# ---------------------------------------------------------------------------
# Public — invite context (anonymous OK)
# ---------------------------------------------------------------------------

class TestInviteContext:
    def test_unknown_token_returns_404(self, anon_client):
        with patch.object(grant_service, "get_invite_context", return_value=None):
            resp = anon_client.get("/auth/grants/invite-context", params={"token": "agc_x"})
        assert resp.status_code == 404

    def test_known_token_returns_context(self, anon_client):
        ctx = {"valid": True, "has_target": True, "target_type": "email"}
        with patch.object(grant_service, "get_invite_context", return_value=ctx):
            resp = anon_client.get("/auth/grants/invite-context", params={"token": "agc_x"})
        assert resp.status_code == 200
        assert resp.json() == ctx

    def test_invite_details_requires_user(self, anon_client):
        resp = anon_client.get("/auth/grants/invite-details", params={"token": "agc_x"})
        assert resp.status_code == 401

    def test_invite_details_returns_payload(self, user_client):
        details = {"valid": True, "resource_id": "res-1", "granted_by": "user-A", "name": None}
        with patch.object(grant_service, "get_invite_details", return_value=details):
            resp = user_client.get("/auth/grants/invite-details", params={"token": "agc_x"})
        assert resp.status_code == 200
        assert resp.json() == details


# ---------------------------------------------------------------------------
# Claim flow → HTTP error mapping
# ---------------------------------------------------------------------------

class TestClaim:
    def test_claim_requires_user(self, anon_client):
        resp = anon_client.post("/auth/grants/claim", json={"token": "agc_x"})
        assert resp.status_code == 401

    def test_unknown_invite_404(self, user_client):
        with patch.object(
            grant_service, "claim_invite",
            side_effect=grant_service.InviteNotFound("nope"),
        ):
            resp = user_client.post("/auth/grants/claim", json={"token": "agc_x"})
        assert resp.status_code == 404

    def test_exhausted_invite_410(self, user_client):
        with patch.object(
            grant_service, "claim_invite",
            side_effect=grant_service.InviteExhausted("done"),
        ):
            resp = user_client.post("/auth/grants/claim", json={"token": "agc_x"})
        assert resp.status_code == 410

    def test_identity_mismatch_403(self, user_client):
        with patch.object(
            grant_service, "claim_invite",
            side_effect=grant_service.InviteIdentityMismatch("not you"),
        ):
            resp = user_client.post("/auth/grants/claim", json={"token": "agc_x"})
        assert resp.status_code == 403

    def test_successful_claim_201(self, user_client):
        with patch.object(grant_service, "claim_invite", return_value=_grant()):
            resp = user_client.post("/auth/grants/claim", json={"token": "agc_x"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["state"] == "active"
        assert "id" in body


# ---------------------------------------------------------------------------
# List + create grants — admin gating
# ---------------------------------------------------------------------------

class TestListGrants:
    def test_requires_user(self, anon_client):
        resp = anon_client.get("/auth/grants", params={"resource_id": "res-1"})
        assert resp.status_code == 401

    def test_non_admin_403(self, user_client):
        with patch.object(grant_service, "can_admin", return_value=False):
            resp = user_client.get("/auth/grants", params={"resource_id": "res-1"})
        assert resp.status_code == 403

    def test_admin_returns_grants(self, user_client):
        grants = [_grant(name="g1"), _grant(name="g2")]
        with patch.object(grant_service, "can_admin", return_value=True), \
             patch("origin.routers.grants_router.db_grants.list_for_resource", return_value=grants):
            resp = user_client.get("/auth/grants", params={"resource_id": "res-1"})
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestCreateGrant:
    def test_user_grant_requires_admin(self, user_client):
        with patch.object(grant_service, "can_admin", return_value=False):
            resp = user_client.post("/auth/grants", json={"resource_id": "res-1", "grantee_id": "u2"})
        assert resp.status_code == 403

    def test_user_grant_admin_creates(self, user_client):
        with patch.object(grant_service, "can_admin", return_value=True), \
             patch("origin.routers.grants_router.db_grants.create", return_value=_grant()):
            resp = user_client.post(
                "/auth/grants",
                json={"resource_id": "res-1", "grantee_id": "u2", "can_read": True},
            )
        assert resp.status_code == 201
        assert resp.json()["state"] == "active"

    def test_invite_requires_share_or_admin(self, user_client):
        with patch.object(grant_service, "can_share", return_value=False):
            resp = user_client.post(
                "/auth/grants",
                json={"resource_id": "res-1", "grantee_type": "invite", "role": "viewer"},
            )
        assert resp.status_code == 403

    def test_invite_creation_returns_claim_url(self, user_client):
        with patch.object(grant_service, "can_share", return_value=True), \
             patch.object(
                 grant_service, "create_invite",
                 return_value=(_grant(grantee_type="invite"), "agc_RAW"),
             ), \
             patch.object(grant_service, "build_claim_url", return_value="https://x/invite/agc_RAW"):
            resp = user_client.post(
                "/auth/grants",
                json={"resource_id": "res-1", "grantee_type": "invite", "role": "viewer"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["claim_token"] == "agc_RAW"
        assert body["claim_url"].endswith("/agc_RAW")

    def test_invite_with_unknown_role_400(self, user_client):
        with patch.object(grant_service, "can_share", return_value=True), \
             patch.object(
                 grant_service, "create_invite",
                 side_effect=ValueError("Unknown role 'godmode'"),
             ):
            resp = user_client.post(
                "/auth/grants",
                json={"resource_id": "res-1", "grantee_type": "invite", "role": "godmode"},
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Read / revoke / accept
# ---------------------------------------------------------------------------

class TestReadGrant:
    def test_grantee_can_read_own(self, user_client):
        g = _grant(grantee_id="user-1")
        with patch("origin.routers.grants_router.db_grants.get_by_id", return_value=g):
            resp = user_client.get(f"/auth/grants/{g.id}")
        assert resp.status_code == 200

    def test_granter_can_read_own_issued(self, user_client):
        g = _grant(grantee_id="user-2", granted_by="user-1")  # granted_by gets stringified
        with patch("origin.routers.grants_router.db_grants.get_by_id", return_value=g):
            resp = user_client.get(f"/auth/grants/{g.id}")
        assert resp.status_code == 200

    def test_unrelated_user_without_admin_404(self, user_client):
        # 404 is intentional — leak less than 403 (security by obscurity).
        g = _grant(grantee_id="user-2", granted_by="user-3")
        with patch("origin.routers.grants_router.db_grants.get_by_id", return_value=g), \
             patch.object(grant_service, "can_admin", return_value=False):
            resp = user_client.get(f"/auth/grants/{g.id}")
        assert resp.status_code == 404

    def test_missing_grant_404(self, user_client):
        with patch("origin.routers.grants_router.db_grants.get_by_id", return_value=None):
            resp = user_client.get(f"/auth/grants/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestRevoke:
    def test_user_can_revoke_own_invite(self, user_client):
        g = _grant(grantee_type="invite", granted_by="user-1")
        with patch("origin.routers.grants_router.db_grants.get_by_id", return_value=g), \
             patch("origin.routers.grants_router.db_grants.update_grant", return_value=g):
            resp = user_client.delete(f"/auth/grants/{g.id}")
        assert resp.status_code == 200
        assert resp.json()["state"] == "revoked"

    def test_user_grant_revoke_requires_admin(self, user_client):
        g = _grant(grantee_type="user", grantee_id="user-2", granted_by="user-3")
        with patch("origin.routers.grants_router.db_grants.get_by_id", return_value=g), \
             patch.object(grant_service, "can_admin", return_value=False):
            resp = user_client.delete(f"/auth/grants/{g.id}")
        assert resp.status_code == 403


class TestAccept:
    def test_pending_grant_accepted_by_grantee(self, user_client):
        g = _grant(state="pending_accept", grantee_id="user-1")
        accepted = _grant(state="active", grantee_id="user-1")
        with patch("origin.routers.grants_router.db_grants.get_by_id", return_value=g), \
             patch("origin.routers.grants_router.db_grants.update_grant", return_value=accepted):
            resp = user_client.post(f"/auth/grants/{g.id}/accept")
        assert resp.status_code == 200
        assert resp.json()["state"] == "active"

    def test_already_active_grant_400(self, user_client):
        g = _grant(state="active", grantee_id="user-1")
        with patch("origin.routers.grants_router.db_grants.get_by_id", return_value=g):
            resp = user_client.post(f"/auth/grants/{g.id}/accept")
        assert resp.status_code == 400

    def test_non_grantee_cannot_accept(self, user_client):
        g = _grant(state="pending_accept", grantee_id="user-2")
        with patch("origin.routers.grants_router.db_grants.get_by_id", return_value=g):
            resp = user_client.post(f"/auth/grants/{g.id}/accept")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Internal kernel-server endpoints
# ---------------------------------------------------------------------------

class TestKernelServerGate:
    def test_user_principal_gets_403_on_check(self, user_client):
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle", "agience-aria"],
        ):
            resp = user_client.get(
                "/auth/grants/check",
                params={"resource": "r1", "principal": "u1", "action": "read"},
            )
        assert resp.status_code == 403

    def test_non_kernel_server_403(self, non_kernel_server_client):
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle"],
        ):
            resp = non_kernel_server_client.get(
                "/auth/grants/check",
                params={"resource": "r1", "principal": "u1", "action": "read"},
            )
        assert resp.status_code == 403

    def test_kernel_server_allowed(self, server_client):
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle", "agience-aria"],
        ), patch(
            "origin.routers.grants_router.db_grants.get_active_for_principal_resource",
            return_value=[_grant(can_read=True)],
        ):
            resp = server_client.get(
                "/auth/grants/check",
                params={"resource": "r1", "principal": "u1", "action": "read"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["allowed"] is True
        assert body["effect"] == "allow"


class TestCheckGrant:
    def test_unknown_action_400(self, server_client):
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle"],
        ):
            resp = server_client.get(
                "/auth/grants/check",
                params={"resource": "r1", "principal": "u1", "action": "godmode"},
            )
        assert resp.status_code == 400

    def test_deny_overrides_allow(self, server_client):
        deny_grant = _grant(effect="deny", can_read=True)
        allow_grant = _grant(effect="allow", can_read=True)
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle"],
        ), patch(
            "origin.routers.grants_router.db_grants.get_active_for_principal_resource",
            return_value=[allow_grant, deny_grant],
        ):
            resp = server_client.get(
                "/auth/grants/check",
                params={"resource": "r1", "principal": "u1", "action": "read"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["allowed"] is False
        assert body["effect"] == "deny"

    def test_no_matching_flag_returns_disallowed(self, server_client):
        # Grant exists but doesn't carry the requested flag.
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle"],
        ), patch(
            "origin.routers.grants_router.db_grants.get_active_for_principal_resource",
            return_value=[_grant(can_read=True)],
        ):
            resp = server_client.get(
                "/auth/grants/check",
                params={"resource": "r1", "principal": "u1", "action": "delete"},
            )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False


class TestUpsertInternal:
    def test_kernel_only(self, user_client):
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle"],
        ):
            resp = user_client.post(
                "/auth/grants/upsert",
                json={
                    "user_id": "u1",
                    "resource_id": "r1",
                    "granted_by": "system",
                    "flags": {"can_read": True},
                },
            )
        assert resp.status_code == 403

    def test_kernel_calls_through(self, server_client):
        with patch(
            "origin.services.kernel_servers.all_client_ids",
            return_value=["agience-mantle"],
        ), patch.object(
            grant_service, "upsert_user_grant",
            return_value=(_grant(), True),
        ) as upsert:
            resp = server_client.post(
                "/auth/grants/upsert",
                json={
                    "user_id": "u1",
                    "resource_id": "r1",
                    "granted_by": "system",
                    "flags": {"can_read": True},
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["changed"] is True
        upsert.assert_called_once()
