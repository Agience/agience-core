"""Unit tests for services.passkey_service.

Heavy WebAuthn ceremony verification is delegated to py_webauthn and is
intentionally NOT re-tested here. We cover:
  - base64url codec helpers (round-trip + padding)
  - _get_rp_id derivation from BACKEND_URI
  - get_registration_options shape (challenge, rp, user, exclude list)
  - get_authentication_options no-passkey-user → None
  - get_authentication_options builds allow list from stored creds
  - verify_registration: stores credential after py_webauthn validates
  - verify_authentication: success updates sign_count, missing cred returns None,
    py_webauthn failure returns None
  - list_credentials / delete_credential / has_passkeys thin wrappers
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import passkey_service


# ---------------------------------------------------------------------------
# base64url helpers
# ---------------------------------------------------------------------------

class TestB64UrlHelpers:
    def test_round_trip(self):
        for raw in (b"", b"x", b"hello world", b"\x00\xff" * 8):
            encoded = passkey_service._b64url_encode(raw)
            assert passkey_service._b64url_decode(encoded) == raw

    def test_no_padding_in_encoded_output(self):
        assert "=" not in passkey_service._b64url_encode(b"abc")

    def test_decode_handles_unpadded_input(self):
        # _b64url_encode strips padding; _b64url_decode must add it back.
        assert passkey_service._b64url_decode("aGVsbG8") == b"hello"


# ---------------------------------------------------------------------------
# RP id derivation
# ---------------------------------------------------------------------------

class TestRpId:
    def test_derives_hostname_from_backend_uri(self):
        with patch("core.config.BACKEND_URI", "https://api.example.com:8443"):
            assert passkey_service._get_rp_id() == "api.example.com"

    def test_falls_back_to_localhost(self):
        with patch("core.config.BACKEND_URI", ""):
            assert passkey_service._get_rp_id() == "localhost"


# ---------------------------------------------------------------------------
# Registration options
# ---------------------------------------------------------------------------

class TestRegistrationOptions:
    def test_includes_challenge_and_user_fields(self):
        with (
            patch(
                "db.arango_identity.get_passkey_credentials_for_person", return_value=[]
            ),
            patch("services.platform_settings_service.settings.get", return_value="Agience"),
        ):
            opts = passkey_service.get_registration_options(
                MagicMock(), "user-1", "u@e.com"
            )
        assert "challenge" in opts and opts["challenge"]
        assert opts["user"]["name"] == "u@e.com"
        assert opts["rp"]["name"] == "Agience"
        assert opts["excludeCredentials"] == []
        # Server-side challenge included for verification.
        assert opts["_challenge"] == opts["challenge"]

    def test_exclude_credentials_built_from_existing(self):
        existing = [{"id": passkey_service._b64url_encode(b"cred-bytes-1"), "transports": ["usb"]}]
        with (
            patch(
                "db.arango_identity.get_passkey_credentials_for_person", return_value=existing
            ),
            patch("services.platform_settings_service.settings.get", return_value="Agience"),
        ):
            opts = passkey_service.get_registration_options(
                MagicMock(), "user-1", "u@e.com"
            )
        assert len(opts["excludeCredentials"]) == 1
        assert opts["excludeCredentials"][0]["transports"] == ["usb"]


# ---------------------------------------------------------------------------
# Authentication options
# ---------------------------------------------------------------------------

class TestAuthenticationOptions:
    def test_returns_none_when_email_unknown(self):
        with patch("db.arango_identity.get_person_by_email", return_value=None):
            assert (
                passkey_service.get_authentication_options(MagicMock(), "u@e.com") is None
            )

    def test_returns_none_when_user_has_no_passkeys(self):
        with (
            patch(
                "db.arango_identity.get_person_by_email", return_value={"id": "user-1"}
            ),
            patch(
                "db.arango_identity.get_passkey_credentials_for_person", return_value=[]
            ),
        ):
            assert (
                passkey_service.get_authentication_options(MagicMock(), "u@e.com") is None
            )

    def test_builds_allow_list_from_stored_credentials(self):
        creds = [
            {
                "id": passkey_service._b64url_encode(b"c1"),
                "transports": ["internal"],
            },
            {
                "id": passkey_service._b64url_encode(b"c2"),
                "transports": [],
            },
        ]
        with (
            patch(
                "db.arango_identity.get_person_by_email", return_value={"id": "user-1"}
            ),
            patch(
                "db.arango_identity.get_passkey_credentials_for_person", return_value=creds
            ),
        ):
            opts = passkey_service.get_authentication_options(MagicMock(), "u@e.com")
        assert opts is not None
        assert len(opts["allowCredentials"]) == 2
        assert opts["_user_id"] == "user-1"


# ---------------------------------------------------------------------------
# Registration / authentication verification
# ---------------------------------------------------------------------------

class TestVerifyRegistration:
    def test_stores_credential_after_py_webauthn_validates(self):
        verification = SimpleNamespace(
            credential_id=b"cred-bytes",
            credential_public_key=b"public-key-bytes",
            sign_count=0,
        )
        captured = {}

        def fake_create(db, doc):
            captured.update(doc)

        with (
            patch("services.passkey_service.RegistrationCredential"),
            patch(
                "services.passkey_service.verify_registration_response",
                return_value=verification,
            ),
            patch(
                "db.arango_identity.create_passkey_credential", side_effect=fake_create
            ),
        ):
            out = passkey_service.verify_registration(
                MagicMock(),
                user_id="user-1",
                credential={"response": {"transports": ["usb"]}},
                expected_challenge=b"challenge",
                device_name="YubiKey",
            )

        assert out["device_name"] == "YubiKey"
        assert out["credential_id"] == passkey_service._b64url_encode(b"cred-bytes")
        assert captured["person_id"] == "user-1"
        assert captured["device_name"] == "YubiKey"
        assert captured["sign_count"] == 0


class TestVerifyAuthentication:
    def test_returns_none_when_credential_not_stored(self):
        fake_cls = MagicMock()
        fake_cls.model_validate.return_value = SimpleNamespace(raw_id=b"cred-bytes")
        with (
            patch("services.passkey_service.AuthenticationCredential", fake_cls),
            patch(
                "db.arango_identity.get_passkey_credential_by_id_and_person",
                return_value=None,
            ),
        ):
            out = passkey_service.verify_authentication(
                MagicMock(),
                credential={},
                expected_challenge=b"c",
                expected_user_id="user-1",
            )
        assert out is None

    def test_success_updates_sign_count_and_returns_person_id(self):
        verification = SimpleNamespace(new_sign_count=5)
        stored = {
            "id": "cred-id",
            "person_id": "user-1",
            "public_key": passkey_service._b64url_encode(b"pk"),
            "sign_count": 0,
        }
        captured = {}

        def fake_update(db, cred_id, patch_doc):
            captured["cred_id"] = cred_id
            captured["patch"] = patch_doc

        fake_cls = MagicMock()
        fake_cls.model_validate.return_value = SimpleNamespace(raw_id=b"raw")
        with (
            patch("services.passkey_service.AuthenticationCredential", fake_cls),
            patch(
                "db.arango_identity.get_passkey_credential_by_id_and_person",
                return_value=stored,
            ),
            patch(
                "services.passkey_service.verify_authentication_response",
                return_value=verification,
            ),
            patch(
                "db.arango_identity.update_passkey_credential", side_effect=fake_update
            ),
        ):
            out = passkey_service.verify_authentication(
                MagicMock(),
                credential={},
                expected_challenge=b"c",
                expected_user_id="user-1",
            )

        assert out == "user-1"
        assert captured["patch"]["sign_count"] == 5
        assert "last_used_at" in captured["patch"]

    def test_py_webauthn_exception_returns_none(self):
        stored = {
            "id": "cred-id",
            "person_id": "user-1",
            "public_key": passkey_service._b64url_encode(b"pk"),
            "sign_count": 0,
        }
        fake_cls = MagicMock()
        fake_cls.model_validate.return_value = SimpleNamespace(raw_id=b"raw")
        with (
            patch("services.passkey_service.AuthenticationCredential", fake_cls),
            patch(
                "db.arango_identity.get_passkey_credential_by_id_and_person",
                return_value=stored,
            ),
            patch(
                "services.passkey_service.verify_authentication_response",
                side_effect=Exception("invalid signature"),
            ),
        ):
            out = passkey_service.verify_authentication(
                MagicMock(),
                credential={},
                expected_challenge=b"c",
                expected_user_id="user-1",
            )
        assert out is None


# ---------------------------------------------------------------------------
# Management wrappers
# ---------------------------------------------------------------------------

class TestManagement:
    def test_list_credentials_projects_safe_fields(self):
        creds = [
            {
                "id": "c-1",
                "person_id": "user-1",
                "public_key": "should-not-leak",
                "device_name": "MacBook",
                "created_time": "t0",
                "last_used_at": "t1",
            }
        ]
        with patch(
            "db.arango_identity.get_passkey_credentials_for_person", return_value=creds
        ):
            out = passkey_service.list_credentials(MagicMock(), "user-1")
        assert out == [
            {
                "credential_id": "c-1",
                "device_name": "MacBook",
                "created_at": "t0",
                "last_used_at": "t1",
            }
        ]
        # Public key MUST NOT be projected.
        assert "public_key" not in out[0]

    def test_has_passkeys_false_for_unknown_email(self):
        with patch("db.arango_identity.get_person_by_email", return_value=None):
            assert passkey_service.has_passkeys(MagicMock(), "u@e.com") is False

    def test_has_passkeys_true_when_credentials_exist(self):
        with (
            patch(
                "db.arango_identity.get_person_by_email", return_value={"id": "u-1"}
            ),
            patch(
                "db.arango_identity.get_passkey_credentials_for_person",
                return_value=[{"id": "c-1"}],
            ),
        ):
            assert passkey_service.has_passkeys(MagicMock(), "u@e.com") is True

    def test_delete_credential_delegates(self):
        with patch(
            "db.arango_identity.delete_passkey_credential_for_person",
            return_value=True,
        ) as d:
            assert passkey_service.delete_credential(MagicMock(), "u-1", "c-1") is True
        d.assert_called_once()
