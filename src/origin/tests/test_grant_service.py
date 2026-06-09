"""Unit tests for `origin.services.grant_service`.

These mock `origin.db.grants` so they run without a live Postgres. They
cover:
- Role-preset → flag matrix translation
- `user_has_any_flag` / `can_share` / `can_admin` flag evaluation
- Invite creation: token issuance, expiry parsing, email opt-in path
- Invite claim flow: target match, exhaustion, single-use revocation
- `upsert_user_grant` idempotency
- Claim error taxonomy (NotFound / Exhausted / IdentityMismatch)

The grant module is the platform's authorization boundary, so these
tests guard against regression in the security-critical paths.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from origin.services import grant_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grant(**overrides) -> SimpleNamespace:
    """Build a Grant-shaped SimpleNamespace for fast tests."""
    defaults = dict(
        id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        grantee_type="user",
        grantee_id="user-1",
        granted_by="user-A",
        state="active",
        can_create=False,
        can_read=False,
        can_update=False,
        can_delete=False,
        can_evict=False,
        can_invoke=False,
        can_add=False,
        can_share=False,
        can_admin=False,
        requires_identity=False,
        target_entity=None,
        target_entity_type=None,
        max_claims=None,
        claims_count=0,
        name=None,
        notes=None,
        expires_at=None,
        granted_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Role presets
# ---------------------------------------------------------------------------

class TestRolePresets:
    def test_viewer_only_has_read(self):
        flags = grant_service.permissions_for_role("viewer")
        assert flags == {"can_read": True}

    def test_editor_includes_crud(self):
        flags = grant_service.permissions_for_role("editor")
        assert flags["can_create"] is True
        assert flags["can_read"] is True
        assert flags["can_update"] is True
        assert flags["can_delete"] is True
        assert flags["can_evict"] is True
        # Sharing + invocation NOT in editor.
        assert "can_share" not in flags
        assert "can_invoke" not in flags
        assert "can_admin" not in flags

    def test_collaborator_includes_share_and_invoke(self):
        flags = grant_service.permissions_for_role("collaborator")
        assert flags["can_share"] is True
        assert flags["can_invoke"] is True
        # Admin still gated.
        assert "can_admin" not in flags

    def test_admin_includes_everything_useful(self):
        flags = grant_service.permissions_for_role("admin")
        assert flags["can_admin"] is True
        assert flags["can_share"] is True
        assert flags["can_invoke"] is True
        assert flags["can_create"] is True

    def test_unknown_role_raises(self):
        with pytest.raises(ValueError, match="Unknown role"):
            grant_service.permissions_for_role("godmode")


# ---------------------------------------------------------------------------
# Flag evaluation helpers
# ---------------------------------------------------------------------------

class TestFlagEvaluation:
    def test_user_has_any_flag_returns_false_for_empty_user_id(self):
        with patch("origin.services.grant_service.db_grants.get_active_for_principal_resource") as q:
            assert grant_service.user_has_any_flag(MagicMock(), "", "res-1", "can_read") is False
            q.assert_not_called()  # short-circuited before DB hit

    def test_user_has_any_flag_true_when_at_least_one_grant_has_flag(self):
        with patch(
            "origin.services.grant_service.db_grants.get_active_for_principal_resource",
            return_value=[_grant(can_read=False), _grant(can_read=True)],
        ):
            assert grant_service.user_has_any_flag(
                MagicMock(), "user-1", "res-1", "can_read"
            ) is True

    def test_user_has_any_flag_false_when_no_grant_has_flag(self):
        with patch(
            "origin.services.grant_service.db_grants.get_active_for_principal_resource",
            return_value=[_grant(can_read=False), _grant(can_update=True)],
        ):
            assert grant_service.user_has_any_flag(
                MagicMock(), "user-1", "res-1", "can_read"
            ) is False

    def test_can_share_or_admin_either_passes(self):
        with patch(
            "origin.services.grant_service.db_grants.get_active_for_principal_resource",
            return_value=[_grant(can_admin=True)],
        ):
            assert grant_service.can_share(MagicMock(), "user-1", "res-1") is True

    def test_can_admin_strict(self):
        with patch(
            "origin.services.grant_service.db_grants.get_active_for_principal_resource",
            return_value=[_grant(can_share=True, can_admin=False)],
        ):
            assert grant_service.can_admin(MagicMock(), "user-1", "res-1") is False


# ---------------------------------------------------------------------------
# Invite creation
# ---------------------------------------------------------------------------

class TestCreateInvite:
    def test_creates_invite_grant_with_role_preset(self):
        captured = {}

        def fake_create(_db, fields):
            captured["fields"] = fields
            return _grant(**{k: v for k, v in fields.items() if k != "id"})

        with patch("origin.services.grant_service.db_grants.create", side_effect=fake_create):
            _, raw_token = grant_service.create_invite(
                MagicMock(),
                user_id="user-A",
                resource_id="res-1",
                role="editor",
                send_email=False,
            )

        assert raw_token.startswith("agc_")
        fields = captured["fields"]
        assert fields["grantee_type"] == "invite"
        assert fields["state"] == "active"
        # editor preset surface:
        assert fields["can_create"] is True
        assert fields["can_update"] is True
        assert fields["can_delete"] is True
        # Editor does NOT include share/invoke/admin:
        assert fields["can_share"] is False
        assert fields["can_invoke"] is False
        assert fields["can_admin"] is False

    def test_token_is_hashed_into_grantee_id(self):
        captured = {}

        def fake_create(_db, fields):
            captured["fields"] = fields
            return _grant()

        with patch("origin.services.grant_service.db_grants.create", side_effect=fake_create):
            _, raw_token = grant_service.create_invite(
                MagicMock(),
                user_id="user-A",
                resource_id="res-1",
                send_email=False,
            )

        # grantee_id is sha256(raw_token), never the raw token itself.
        assert captured["fields"]["grantee_id"] != raw_token
        assert len(captured["fields"]["grantee_id"]) == 64  # sha256 hex

    def test_target_email_lowercased_and_requires_identity(self):
        captured = {}

        def fake_create(_db, fields):
            captured["fields"] = fields
            return _grant()

        with patch("origin.services.grant_service.db_grants.create", side_effect=fake_create), \
             patch("origin.services.grant_service._send_invite_email", return_value=False):
            grant_service.create_invite(
                MagicMock(),
                user_id="user-A",
                resource_id="res-1",
                target_email="Alice@Example.COM",
                send_email=False,
            )

        assert captured["fields"]["target_entity"] == "alice@example.com"
        assert captured["fields"]["target_entity_type"] == "email"
        assert captured["fields"]["requires_identity"] is True

    def test_send_email_only_called_when_email_present_and_opted_in(self):
        with patch("origin.services.grant_service.db_grants.create", return_value=_grant()), \
             patch("origin.services.grant_service._send_invite_email") as send:
            grant_service.create_invite(
                MagicMock(),
                user_id="user-A",
                resource_id="res-1",
                target_email="alice@example.com",
                send_email=False,
            )
            send.assert_not_called()

        with patch("origin.services.grant_service.db_grants.create", return_value=_grant()), \
             patch("origin.services.grant_service._send_invite_email", return_value=True) as send:
            grant_service.create_invite(
                MagicMock(),
                user_id="user-A",
                resource_id="res-1",
                target_email="alice@example.com",
                send_email=True,
            )
            send.assert_called_once()

    def test_expires_at_iso_parsed(self):
        captured = {}

        def fake_create(_db, fields):
            captured["fields"] = fields
            return _grant()

        with patch("origin.services.grant_service.db_grants.create", side_effect=fake_create):
            grant_service.create_invite(
                MagicMock(),
                user_id="user-A",
                resource_id="res-1",
                expires_at="2030-01-01T00:00:00Z",
                send_email=False,
            )

        assert captured["fields"]["expires_at"].year == 2030


# ---------------------------------------------------------------------------
# Invite claim
# ---------------------------------------------------------------------------

class TestClaimInvite:
    def test_unknown_token_raises_not_found(self):
        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[],
        ):
            with pytest.raises(grant_service.InviteNotFound):
                grant_service.claim_invite(MagicMock(), "user-1", "agc_bogus")

    def test_token_pointing_at_non_invite_grant_raises_not_found(self):
        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[_grant(grantee_type="user")],  # not an invite
        ):
            with pytest.raises(grant_service.InviteNotFound):
                grant_service.claim_invite(MagicMock(), "user-1", "agc_bogus")

    def test_revoked_invite_raises_exhausted(self):
        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[_grant(grantee_type="invite", state="revoked")],
        ):
            with pytest.raises(grant_service.InviteExhausted):
                grant_service.claim_invite(MagicMock(), "user-1", "agc_token")

    def test_max_claims_reached_raises_exhausted(self):
        invite = _grant(
            grantee_type="invite",
            state="active",
            max_claims=2,
            claims_count=2,
        )
        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[invite],
        ):
            with pytest.raises(grant_service.InviteExhausted):
                grant_service.claim_invite(MagicMock(), "user-1", "agc_token")

    def test_target_email_mismatch_raises_identity(self):
        invite = _grant(
            grantee_type="invite",
            state="active",
            target_entity="alice@example.com",
            target_entity_type="email",
            max_claims=1,
        )
        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[invite],
        ), patch(
            "origin.db.persons.get_by_id",
            return_value=SimpleNamespace(email="bob@example.com"),
        ):
            with pytest.raises(grant_service.InviteIdentityMismatch):
                grant_service.claim_invite(MagicMock(), "user-bob", "agc_token")

    def test_single_claim_invite_revokes_after_use(self):
        invite = _grant(
            grantee_type="invite",
            state="active",
            max_claims=1,
            claims_count=0,
            target_entity=None,
        )
        captured_updates: list[dict] = []

        def fake_update(_db, _gid, fields):
            captured_updates.append(fields)
            return None

        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[invite],
        ), patch(
            "origin.services.grant_service.db_grants.create",
            return_value=_grant(),
        ), patch(
            "origin.services.grant_service.db_grants.update_grant",
            side_effect=fake_update,
        ):
            grant_service.claim_invite(MagicMock(), "user-1", "agc_token")

        assert len(captured_updates) == 1
        update = captured_updates[0]
        assert update["claims_count"] == 1
        # max_claims == 1 → invite gets auto-revoked.
        assert update["state"] == "revoked"
        assert update["revoked_by"] == "user-1"

    def test_multi_claim_invite_increments_count_without_revoking(self):
        invite = _grant(
            grantee_type="invite",
            state="active",
            max_claims=5,
            claims_count=2,
            target_entity=None,
        )
        captured_updates: list[dict] = []

        def fake_update(_db, _gid, fields):
            captured_updates.append(fields)
            return None

        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[invite],
        ), patch(
            "origin.services.grant_service.db_grants.create",
            return_value=_grant(),
        ), patch(
            "origin.services.grant_service.db_grants.update_grant",
            side_effect=fake_update,
        ):
            grant_service.claim_invite(MagicMock(), "user-1", "agc_token")

        update = captured_updates[0]
        assert update["claims_count"] == 3
        # Multi-claim invite stays active.
        assert "state" not in update


# ---------------------------------------------------------------------------
# Pre/post-auth context
# ---------------------------------------------------------------------------

class TestInviteContext:
    def test_get_invite_context_returns_none_for_unknown_token(self):
        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[],
        ):
            assert grant_service.get_invite_context(MagicMock(), "agc_x") is None

    def test_get_invite_context_reports_target_presence(self):
        invite = _grant(
            grantee_type="invite",
            state="active",
            target_entity="alice@example.com",
            target_entity_type="email",
        )
        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[invite],
        ):
            ctx = grant_service.get_invite_context(MagicMock(), "agc_x")
        assert ctx == {"valid": True, "has_target": True, "target_type": "email"}

    def test_get_invite_details_flags_identity_mismatch(self):
        invite = _grant(
            grantee_type="invite",
            state="active",
            target_entity="alice@example.com",
            target_entity_type="email",
        )
        with patch(
            "origin.services.grant_service.db_grants.get_active_by_key",
            return_value=[invite],
        ), patch(
            "origin.db.persons.get_by_id",
            return_value=SimpleNamespace(email="bob@example.com"),
        ):
            details = grant_service.get_invite_details(MagicMock(), "agc_x", "user-bob")
        assert details == {"valid": True, "identity_mismatch": True}


# ---------------------------------------------------------------------------
# upsert_user_grant
# ---------------------------------------------------------------------------

class TestUpsertUserGrant:
    def test_creates_when_no_existing_grant(self):
        with patch(
            "origin.services.grant_service.db_grants.find_existing_user_grant",
            return_value=None,
        ), patch(
            "origin.services.grant_service.db_grants.create",
            return_value=_grant(),
        ) as create:
            _, changed = grant_service.upsert_user_grant(
                MagicMock(),
                user_id="user-1",
                resource_id="res-1",
                granted_by="user-A",
                flags={"can_read": True},
            )
        assert changed is True
        create.assert_called_once()

    def test_idempotent_when_flags_match(self):
        existing = _grant(can_read=True)
        with patch(
            "origin.services.grant_service.db_grants.find_existing_user_grant",
            return_value=existing,
        ), patch(
            "origin.services.grant_service.db_grants.update_grant",
        ) as update:
            grant, changed = grant_service.upsert_user_grant(
                MagicMock(),
                user_id="user-1",
                resource_id="res-1",
                granted_by="user-A",
                flags={"can_read": True},
            )
        assert changed is False
        assert grant is existing
        update.assert_not_called()

    def test_updates_when_flags_diverge(self):
        existing = _grant(can_read=True, can_update=False)
        with patch(
            "origin.services.grant_service.db_grants.find_existing_user_grant",
            return_value=existing,
        ), patch(
            "origin.services.grant_service.db_grants.update_grant",
            return_value=_grant(can_read=True, can_update=True),
        ) as update:
            _, changed = grant_service.upsert_user_grant(
                MagicMock(),
                user_id="user-1",
                resource_id="res-1",
                granted_by="user-A",
                flags={"can_read": True, "can_update": True},
            )
        assert changed is True
        update.assert_called_once()
