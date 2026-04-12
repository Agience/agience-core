"""Unit tests for services.person_service.

Covers identity-tier wrappers and the OAuth/password user lifecycle:
  - get_user_by_*: None when missing, hydrated entity when present
  - create_person: surfaces password_hash, raises on db failure
  - update_person: surfaces password_hash, raises on db failure
  - get_or_create_user_by_oidc_identity: existing match (with diff sync),
    new user provisioning, allow-list rejection
  - create_user_with_password: required username, allow-list, conflict detection
  - get_or_create_user_by_email: format validation, idempotent existing user
  - link_oidc_identity: collision detection, idempotent re-link, blocks
    re-linking when account already has an identity
  - unlink_oidc_identity: requires password fallback
  - update_person_preferences: deep merge
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from entities.person import Person
from services import person_service


def _person_doc(**overrides) -> dict:
    base = {
        "id": "user-1",
        "email": "u@e.com",
        "name": "User",
        "picture": None,
        "google_id": "",
        "oidc_provider": "",
        "oidc_subject": "",
        "preferences": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

class TestLookups:
    def test_get_by_id_returns_none_when_missing(self):
        with patch("db.arango_identity.get_person_by_id", return_value=None):
            assert person_service.get_user_by_id(MagicMock(), "user-1") is None

    def test_get_by_id_returns_entity(self):
        with patch(
            "db.arango_identity.get_person_by_id", return_value=_person_doc()
        ):
            p = person_service.get_user_by_id(MagicMock(), "user-1")
        assert isinstance(p, Person)
        assert p.email == "u@e.com"

    def test_get_by_email_returns_none(self):
        with patch("db.arango_identity.get_person_by_email", return_value=None):
            assert person_service.get_user_by_email(MagicMock(), "x") is None

    def test_get_by_username_returns_entity(self):
        with patch(
            "db.arango_identity.get_person_by_username",
            return_value=_person_doc(),
        ):
            assert person_service.get_user_by_username(MagicMock(), "u") is not None

    def test_get_by_oidc_identity_returns_entity(self):
        with patch(
            "db.arango_identity.get_person_by_oidc_identity",
            return_value=_person_doc(oidc_provider="google", oidc_subject="123"),
        ):
            p = person_service.get_user_by_oidc_identity(
                MagicMock(), "google", "123"
            )
        assert p is not None
        assert p.oidc_provider == "google"


# ---------------------------------------------------------------------------
# create_person / update_person
# ---------------------------------------------------------------------------

class TestPersonCrud:
    def test_create_person_assigns_id_and_propagates_password_hash(self):
        captured = {}

        def fake_create(db, doc):
            captured.update(doc)
            return "new-id"

        entity = Person(
            email="u@e.com", name="U", picture=None, password_hash="pbkdf2$x"
        )
        with patch("db.arango_identity.create_person", side_effect=fake_create):
            out = person_service.create_person(MagicMock(), entity)
        assert out.id == "new-id"
        assert captured["password_hash"] == "pbkdf2$x"

    def test_create_person_raises_on_db_failure(self):
        with patch("db.arango_identity.create_person", return_value=None):
            with pytest.raises(RuntimeError):
                person_service.create_person(
                    MagicMock(), Person(email="u@e.com", name="U", picture=None)
                )

    def test_update_person_propagates_password_hash(self):
        captured = {}

        def fake_update(db, person_id, updates):
            captured.update(updates)
            return True

        entity = Person(
            id="user-1", email="u@e.com", name="U", picture=None, password_hash="new-hash"
        )
        with patch("db.arango_identity.update_person", side_effect=fake_update):
            person_service.update_person(MagicMock(), entity)
        assert captured["password_hash"] == "new-hash"

    def test_update_person_raises_on_db_failure(self):
        with patch("db.arango_identity.update_person", return_value=False):
            with pytest.raises(RuntimeError):
                person_service.update_person(
                    MagicMock(),
                    Person(id="user-1", email="x", name="x", picture=None),
                )


# ---------------------------------------------------------------------------
# get_or_create_user_by_oidc_identity
# ---------------------------------------------------------------------------

class TestGetOrCreateOidc:
    def test_creates_new_user_when_not_found(self):
        with (
            patch(
                "services.person_service.is_person_allowed", return_value=True
            ),
            patch(
                "services.person_service.get_user_by_oidc_identity",
                return_value=None,
            ),
            patch(
                "services.person_service.create_person",
                side_effect=lambda db, e: (setattr(e, "id", "new-id") or e),
            ),
            patch(
                "services.person_service._provision_new_user_defaults"
            ) as provision,
        ):
            p = person_service.get_or_create_user_by_oidc_identity(
                MagicMock(),
                "google",
                "subj-1",
                "u@e.com",
                "User",
            )
        assert p.id == "new-id"
        assert p.oidc_provider == "google"
        provision.assert_called_once()

    def test_existing_user_returned_unchanged_when_no_diff(self):
        existing = Person(
            id="u-1",
            email="u@e.com",
            name="User",
            picture=None,
            oidc_provider="google",
            oidc_subject="subj-1",
        )
        with (
            patch(
                "services.person_service.is_person_allowed", return_value=True
            ),
            patch(
                "services.person_service.get_user_by_oidc_identity",
                return_value=existing,
            ),
            patch(
                "services.person_service.update_person"
            ) as upd,
        ):
            out = person_service.get_or_create_user_by_oidc_identity(
                MagicMock(),
                "google",
                "subj-1",
                "u@e.com",
                "User",
            )
        assert out is existing
        upd.assert_not_called()

    def test_existing_user_synced_when_email_changed(self):
        existing = Person(
            id="u-1",
            email="old@e.com",
            name="Old",
            picture=None,
            oidc_provider="google",
            oidc_subject="subj-1",
        )
        with (
            patch(
                "services.person_service.is_person_allowed", return_value=True
            ),
            patch(
                "services.person_service.get_user_by_oidc_identity",
                return_value=existing,
            ),
            patch(
                "services.person_service.update_person",
                side_effect=lambda db, e: e,
            ) as upd,
        ):
            out = person_service.get_or_create_user_by_oidc_identity(
                MagicMock(),
                "google",
                "subj-1",
                "new@e.com",
                "New Name",
            )
        upd.assert_called_once()
        assert out.email == "new@e.com"
        assert out.name == "New Name"

    def test_disallowed_user_raises_permission_error(self):
        with patch(
            "services.person_service.is_person_allowed", return_value=False
        ):
            with pytest.raises(PermissionError):
                person_service.get_or_create_user_by_oidc_identity(
                    MagicMock(),
                    "google",
                    "subj-1",
                    "blocked@e.com",
                    "Blocked",
                )


# ---------------------------------------------------------------------------
# create_user_with_password
# ---------------------------------------------------------------------------

class TestCreateUserWithPassword:
    def test_requires_username(self):
        with pytest.raises(ValueError, match="Username is required"):
            person_service.create_user_with_password(
                MagicMock(),
                username="",
                name="X",
                password_hash="h",
            )

    def test_rejects_disallowed_email(self):
        with patch(
            "services.person_service.is_person_allowed", return_value=False
        ):
            with pytest.raises(PermissionError):
                person_service.create_user_with_password(
                    MagicMock(),
                    username="u",
                    name="U",
                    password_hash="h",
                    email="blocked@e.com",
                )

    def test_rejects_taken_username(self):
        with (
            patch(
                "services.person_service.is_person_allowed", return_value=True
            ),
            patch(
                "services.person_service.get_user_by_username",
                return_value=Person(
                    id="x", email="", name="X", picture=None
                ),
            ),
        ):
            with pytest.raises(ValueError, match="Username already taken"):
                person_service.create_user_with_password(
                    MagicMock(),
                    username="u",
                    name="U",
                    password_hash="h",
                )

    def test_rejects_taken_email(self):
        with (
            patch(
                "services.person_service.is_person_allowed", return_value=True
            ),
            patch(
                "services.person_service.get_user_by_username", return_value=None
            ),
            patch(
                "services.person_service.get_user_by_email",
                return_value=Person(
                    id="x", email="u@e.com", name="X", picture=None
                ),
            ),
        ):
            with pytest.raises(ValueError, match="Email already registered"):
                person_service.create_user_with_password(
                    MagicMock(),
                    username="u",
                    name="U",
                    password_hash="h",
                    email="u@e.com",
                )

    def test_happy_path_creates_and_provisions(self):
        with (
            patch(
                "services.person_service.is_person_allowed", return_value=True
            ),
            patch(
                "services.person_service.get_user_by_username", return_value=None
            ),
            patch(
                "services.person_service.get_user_by_email", return_value=None
            ),
            patch(
                "services.person_service.create_person",
                side_effect=lambda db, e: (setattr(e, "id", "new") or e),
            ),
            patch(
                "services.person_service._provision_new_user_defaults"
            ) as provision,
        ):
            out = person_service.create_user_with_password(
                MagicMock(),
                username="alice",
                name="Alice",
                password_hash="h",
                email="alice@e.com",
            )
        assert out.username == "alice"
        provision.assert_called_once()


# ---------------------------------------------------------------------------
# get_or_create_user_by_email
# ---------------------------------------------------------------------------

class TestGetOrCreateByEmail:
    def test_invalid_email_raises(self):
        with pytest.raises(ValueError):
            person_service.get_or_create_user_by_email(
                MagicMock(), email="not-an-email"
            )

    def test_returns_existing_user(self):
        existing = Person(id="u-1", email="u@e.com", name="U", picture=None)
        with (
            patch(
                "services.person_service.is_person_allowed", return_value=True
            ),
            patch(
                "services.person_service.get_user_by_email",
                return_value=existing,
            ),
        ):
            out = person_service.get_or_create_user_by_email(
                MagicMock(), email="u@e.com"
            )
        assert out is existing


# ---------------------------------------------------------------------------
# link / unlink OIDC identity
# ---------------------------------------------------------------------------

class TestLinkOidc:
    def test_already_linked_to_same_user_is_noop(self):
        existing = Person(
            id="u-1",
            email="u@e.com",
            name="U",
            picture=None,
            oidc_provider="google",
            oidc_subject="subj-1",
        )
        with patch(
            "services.person_service.get_user_by_oidc_identity",
            return_value=existing,
        ):
            out = person_service.link_oidc_identity(
                MagicMock(), "u-1", "google", "subj-1"
            )
        assert out is existing

    def test_already_linked_to_other_user_raises(self):
        other = Person(
            id="other",
            email="other@e.com",
            name="Other",
            picture=None,
            oidc_provider="google",
            oidc_subject="subj-1",
        )
        with patch(
            "services.person_service.get_user_by_oidc_identity",
            return_value=other,
        ):
            with pytest.raises(ValueError, match="already linked"):
                person_service.link_oidc_identity(
                    MagicMock(), "u-1", "google", "subj-1"
                )

    def test_user_already_has_identity_raises(self):
        user = Person(
            id="u-1",
            email="u@e.com",
            name="U",
            picture=None,
            oidc_provider="github",
            oidc_subject="subj-other",
        )
        with (
            patch(
                "services.person_service.get_user_by_oidc_identity",
                return_value=None,
            ),
            patch(
                "services.person_service.get_user_by_id", return_value=user
            ),
        ):
            with pytest.raises(ValueError, match="Unlink first"):
                person_service.link_oidc_identity(
                    MagicMock(), "u-1", "google", "subj-1"
                )

    def test_happy_path_links_identity(self):
        user = Person(
            id="u-1", email="u@e.com", name="U", picture=None
        )
        with (
            patch(
                "services.person_service.get_user_by_oidc_identity",
                return_value=None,
            ),
            patch(
                "services.person_service.get_user_by_id", return_value=user
            ),
            patch(
                "services.person_service.update_person",
                side_effect=lambda db, e: e,
            ),
        ):
            out = person_service.link_oidc_identity(
                MagicMock(), "u-1", "google", "subj-1"
            )
        assert out.oidc_provider == "google"
        assert out.google_id == "subj-1"


class TestUnlinkOidc:
    def test_requires_user_exists(self):
        with patch("services.person_service.get_user_by_id", return_value=None):
            with pytest.raises(ValueError, match="User not found"):
                person_service.unlink_oidc_identity(MagicMock(), "missing")

    def test_requires_password_fallback(self):
        user = Person(
            id="u-1",
            email="u@e.com",
            name="U",
            picture=None,
            password_hash=None,
            oidc_provider="google",
            oidc_subject="subj-1",
        )
        with patch("services.person_service.get_user_by_id", return_value=user):
            with pytest.raises(ValueError, match="no password is set"):
                person_service.unlink_oidc_identity(MagicMock(), "u-1")

    def test_requires_existing_link(self):
        user = Person(
            id="u-1",
            email="u@e.com",
            name="U",
            picture=None,
            password_hash="h",
        )
        with patch("services.person_service.get_user_by_id", return_value=user):
            with pytest.raises(ValueError, match="No linked identity"):
                person_service.unlink_oidc_identity(MagicMock(), "u-1")

    def test_happy_path_clears_oidc_fields(self):
        user = Person(
            id="u-1",
            email="u@e.com",
            name="U",
            picture=None,
            password_hash="h",
            oidc_provider="google",
            oidc_subject="subj-1",
        )
        with (
            patch("services.person_service.get_user_by_id", return_value=user),
            patch(
                "services.person_service.update_person",
                side_effect=lambda db, e: e,
            ),
        ):
            out = person_service.unlink_oidc_identity(MagicMock(), "u-1")
        assert out.oidc_provider == ""
        assert out.oidc_subject == ""


# ---------------------------------------------------------------------------
# update_person_preferences
# ---------------------------------------------------------------------------

class TestUpdatePreferences:
    def test_merges_new_with_existing(self):
        captured = {}

        def fake_update(db, pid, prefs):
            captured["prefs"] = prefs
            return True

        with (
            patch(
                "db.arango_identity.get_person_by_id",
                return_value=_person_doc(preferences={"theme": "dark"}),
            ),
            patch(
                "db.arango_identity.update_person_preferences",
                side_effect=fake_update,
            ),
        ):
            person_service.update_person_preferences(
                MagicMock(), "user-1", {"locale": "en"}
            )
        assert captured["prefs"] == {"theme": "dark", "locale": "en"}

    def test_raises_when_person_missing(self):
        with patch(
            "db.arango_identity.get_person_by_id", return_value=None
        ):
            with pytest.raises(ValueError, match="not found"):
                person_service.update_person_preferences(
                    MagicMock(), "missing", {"k": "v"}
                )
