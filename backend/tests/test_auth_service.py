"""Unit tests for services.auth_service.

Covers the cryptographic spine of the auth subsystem:
  - Password hashing (PBKDF2-SHA256) round-trip + verify negative cases
  - JWT issue + verify (`create_jwt_token` / `verify_token`) for the three claim
    shapes documented in CLAUDE.md (user / server / delegation)
  - Audience binding: `verify_token(expected_audience=...)` rejects mismatches
  - Expiry handling
  - JWKS shape
  - PKCE challenge generation + verification matrix
  - API key generate / hash / verify (active, inactive, expired, missing)
  - Inbound nonce: HMAC issue → verify round-trip + binding + expiry tampering
  - find_mcp_client_by_client_id and get_mcp_client_allowed_scopes parsing
  - is_person_allowed allow-list matrix (default-allow, wildcards, glob email/domain)

Note: `is_client_redirect_allowed` and `issue_delegation_token` are exercised
in test_router_auth.py — not duplicated here.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from jose import jwt as _jwt

import core.key_manager as _km
from core import config
from services import auth_service


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_then_verify_round_trip(self):
        h = auth_service.hash_password("correct horse battery staple")
        assert auth_service.verify_password("correct horse battery staple", h)

    def test_verify_rejects_wrong_password(self):
        h = auth_service.hash_password("hunter2")
        assert not auth_service.verify_password("hunter3", h)

    def test_verify_rejects_empty_inputs(self):
        assert not auth_service.verify_password("", "anything")
        assert not auth_service.verify_password("pw", "")

    def test_verify_rejects_garbage_hash(self):
        assert not auth_service.verify_password("pw", "not$a$valid$hash")
        assert not auth_service.verify_password("pw", "wrongalg$1$aa$bb")

    def test_hash_format_starts_with_algorithm_marker(self):
        h = auth_service.hash_password("x")
        assert h.startswith("pbkdf2_sha256$")
        # Format: alg$iters$salt$hash
        assert h.count("$") == 3

    def test_hash_empty_password_raises(self):
        with pytest.raises(ValueError):
            auth_service.hash_password("")

    def test_dummy_verify_does_not_raise(self):
        # Constant-time-equivalent helper used to avoid user enumeration.
        auth_service.dummy_verify_password("anything")
        auth_service.dummy_verify_password("")


# ---------------------------------------------------------------------------
# JWT issue / verify
# ---------------------------------------------------------------------------

class TestJWT:
    def test_create_and_verify_user_token(self):
        token = auth_service.create_jwt_token(
            {"sub": "user-1", "email": "u@e.com", "aud": config.AUTHORITY_ISSUER}
        )
        payload = auth_service.verify_token(token, expected_audience=config.AUTHORITY_ISSUER)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["aud"] == config.AUTHORITY_ISSUER
        assert payload["iss"] == config.AUTHORITY_ISSUER
        assert "exp" in payload and "iat" in payload

    def test_verify_token_rejects_audience_mismatch(self):
        token = auth_service.create_jwt_token({"sub": "u", "aud": "alpha"})
        assert auth_service.verify_token(token, expected_audience="beta") is None

    def test_verify_token_skips_audience_when_caller_omits(self):
        token = auth_service.create_jwt_token({"sub": "u", "aud": "anything"})
        # No expected_audience → verify_aud is disabled, payload returned.
        payload = auth_service.verify_token(token)
        assert payload is not None and payload["aud"] == "anything"

    def test_verify_token_rejects_garbage(self):
        assert auth_service.verify_token("not.a.token") is None

    def test_verify_token_rejects_expired(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        token = auth_service.create_jwt_token(
            {"sub": "u", "aud": "x", "exp": past.timestamp()}
        )
        assert auth_service.verify_token(token, expected_audience="x") is None

    def test_create_jwt_uses_provided_expiry_window(self):
        token = auth_service.create_jwt_token({"sub": "u", "aud": "x"}, expires_hours=1)
        payload = _jwt.decode(
            token,
            _km.get_public_key_pem(),
            algorithms=["RS256"],
            audience="x",
        )
        delta = payload["exp"] - payload["iat"]
        assert 3500 < delta < 3700  # ~1 hour ± a few seconds

    def test_get_jwks_returns_keys_array(self):
        jwks = auth_service.get_jwks()
        assert "keys" in jwks
        assert len(jwks["keys"]) >= 1
        assert "kty" in jwks["keys"][0]


# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------

class TestPKCE:
    def test_generate_then_verify_s256(self):
        verifier, challenge = auth_service.generate_pkce_challenge()
        assert auth_service.verify_pkce_challenge(verifier, challenge, method="S256")

    def test_verify_rejects_wrong_verifier(self):
        _, challenge = auth_service.generate_pkce_challenge()
        assert not auth_service.verify_pkce_challenge("wrong", challenge, method="S256")

    def test_plain_method_round_trip(self):
        assert auth_service.verify_pkce_challenge("foo", "foo", method="plain")
        assert not auth_service.verify_pkce_challenge("foo", "bar", method="plain")

    def test_unknown_method_rejected(self):
        assert not auth_service.verify_pkce_challenge("a", "a", method="md5")


# ---------------------------------------------------------------------------
# OAuth response builders
# ---------------------------------------------------------------------------

class TestOAuthResponses:
    def test_create_authorization_response_includes_state(self):
        url = auth_service.create_authorization_response(
            "code-1", state="abc", redirect_uri="https://app/cb"
        )
        assert url.startswith("https://app/cb?")
        assert "code=code-1" in url
        assert "state=abc" in url

    def test_create_error_response_includes_description(self):
        url = auth_service.create_error_response(
            "invalid_grant",
            error_description="bad",
            redirect_uri="https://app/cb",
        )
        assert "error=invalid_grant" in url
        assert "error_description=bad" in url


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

class TestAPIKey:
    def test_generate_format(self):
        k = auth_service.generate_api_key()
        assert k.startswith("agc_")
        assert len(k) == 4 + 32  # prefix + 32 hex chars

    def test_hash_is_stable(self):
        k = "agc_test"
        assert auth_service.hash_api_key(k) == auth_service.hash_api_key(k)
        assert len(auth_service.hash_api_key(k)) == 64  # sha256 hex

    def test_verify_returns_entity_when_active(self):
        ent = SimpleNamespace(id="k-1", is_active=True, expires_at=None)
        with (
            patch("services.auth_service.get_api_key_by_hash", return_value=ent),
            patch("services.auth_service.update_api_key_last_used") as touch,
        ):
            out = auth_service.verify_api_key(object(), "agc_x")
        assert out is ent
        touch.assert_called_once()

    def test_verify_returns_none_when_unknown(self):
        with patch("services.auth_service.get_api_key_by_hash", return_value=None):
            assert auth_service.verify_api_key(object(), "agc_x") is None

    def test_verify_returns_none_when_inactive(self):
        ent = SimpleNamespace(id="k-1", is_active=False, expires_at=None)
        with patch("services.auth_service.get_api_key_by_hash", return_value=ent):
            assert auth_service.verify_api_key(object(), "agc_x") is None

    def test_verify_returns_none_when_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        ent = SimpleNamespace(id="k-1", is_active=True, expires_at=past)
        with patch("services.auth_service.get_api_key_by_hash", return_value=ent):
            assert auth_service.verify_api_key(object(), "agc_x") is None

    def test_verify_accepts_unparseable_expires_at(self):
        # Bad format → swallowed → key still valid (matches current behavior).
        ent = SimpleNamespace(id="k-1", is_active=True, expires_at="garbage")
        with (
            patch("services.auth_service.get_api_key_by_hash", return_value=ent),
            patch("services.auth_service.update_api_key_last_used"),
        ):
            assert auth_service.verify_api_key(object(), "agc_x") is ent


# ---------------------------------------------------------------------------
# Inbound nonce
# ---------------------------------------------------------------------------

class TestInboundNonce:
    SECRET = "test-nonce-secret"

    def test_round_trip_valid(self):
        token, exp = auth_service.issue_nonce("k-1", "art-1", self.SECRET)
        assert auth_service.verify_nonce(token, "k-1", "art-1", self.SECRET)
        assert exp > datetime.now(timezone.utc)

    def test_binding_to_different_artifact_rejected(self):
        token, _ = auth_service.issue_nonce("k-1", "art-1", self.SECRET)
        assert not auth_service.verify_nonce(token, "k-1", "art-2", self.SECRET)

    def test_binding_to_different_key_rejected(self):
        token, _ = auth_service.issue_nonce("k-1", "art-1", self.SECRET)
        assert not auth_service.verify_nonce(token, "k-2", "art-1", self.SECRET)

    def test_wrong_secret_rejected(self):
        token, _ = auth_service.issue_nonce("k-1", "art-1", self.SECRET)
        assert not auth_service.verify_nonce(token, "k-1", "art-1", "other-secret")

    def test_expired_nonce_rejected(self):
        token, _ = auth_service.issue_nonce("k-1", "art-1", self.SECRET)
        with patch(
            "services.auth_service.time.time",
            return_value=time.time() + auth_service.NONCE_TTL_SECONDS + 60,
        ):
            assert not auth_service.verify_nonce(token, "k-1", "art-1", self.SECRET)

    def test_garbage_token_rejected(self):
        assert not auth_service.verify_nonce("not-base64!", "k", "a", self.SECRET)
        assert not auth_service.verify_nonce("", "k", "a", self.SECRET)

    def test_issue_requires_secret(self):
        with pytest.raises(ValueError):
            auth_service.issue_nonce("k", "a", "")


# ---------------------------------------------------------------------------
# find_mcp_client_by_client_id / get_mcp_client_allowed_scopes
# ---------------------------------------------------------------------------

class TestMcpClientLookup:
    def test_find_returns_redirect_uris_from_artifact_context(self):
        artifact = SimpleNamespace(
            context=json.dumps({"client_id": "c-1", "redirect_uris": ["https://a/cb"]})
        )
        with patch(
            "services.auth_service.find_artifact_by_context_field",
            return_value=artifact,
        ):
            uris = auth_service.find_mcp_client_by_client_id(object(), "c-1")
        assert uris == ["https://a/cb"]

    def test_find_returns_none_when_no_artifact(self):
        with patch(
            "services.auth_service.find_artifact_by_context_field", return_value=None
        ):
            assert auth_service.find_mcp_client_by_client_id(object(), "c-1") is None

    def test_find_returns_empty_list_when_field_missing(self):
        artifact = SimpleNamespace(context=json.dumps({"client_id": "c-1"}))
        with patch(
            "services.auth_service.find_artifact_by_context_field",
            return_value=artifact,
        ):
            assert auth_service.find_mcp_client_by_client_id(object(), "c-1") == []

    def test_get_allowed_scopes_returns_declared_list(self):
        artifact = SimpleNamespace(
            context=json.dumps({"allowed_oauth_scopes": ["read", "write"]})
        )
        with patch(
            "services.auth_service.find_artifact_by_context_field",
            return_value=artifact,
        ):
            scopes = auth_service.get_mcp_client_allowed_scopes(object(), "c-1")
        assert scopes == ["read", "write"]

    def test_get_allowed_scopes_falls_back_to_default(self):
        with patch(
            "services.auth_service.find_artifact_by_context_field", return_value=None
        ):
            scopes = auth_service.get_mcp_client_allowed_scopes(object(), "c-1")
        assert scopes == ["read"]

    def test_get_allowed_scopes_handles_dict_context(self):
        artifact = SimpleNamespace(context={"allowed_oauth_scopes": ["x"]})
        with patch(
            "services.auth_service.find_artifact_by_context_field",
            return_value=artifact,
        ):
            assert auth_service.get_mcp_client_allowed_scopes(object(), "c-1") == ["x"]


# ---------------------------------------------------------------------------
# is_person_allowed
# ---------------------------------------------------------------------------

class TestPersonAllowed:
    def test_default_allow_when_unconfigured(self):
        with (
            patch("core.config.ALLOWED_EMAILS", []),
            patch("core.config.ALLOWED_DOMAINS", []),
            patch("core.config.ALLOWED_GOOGLE_IDS", []),
        ):
            assert auth_service.is_person_allowed(None, "anyone@example.com")

    def test_wildcard_in_emails_opens_access(self):
        with (
            patch("core.config.ALLOWED_EMAILS", ["*"]),
            patch("core.config.ALLOWED_DOMAINS", []),
            patch("core.config.ALLOWED_GOOGLE_IDS", []),
        ):
            assert auth_service.is_person_allowed(None, "anyone@example.com")

    def test_exact_email_match(self):
        with (
            patch("core.config.ALLOWED_EMAILS", ["bob@example.com"]),
            patch("core.config.ALLOWED_DOMAINS", []),
            patch("core.config.ALLOWED_GOOGLE_IDS", []),
        ):
            assert auth_service.is_person_allowed(None, "bob@example.com")
            assert not auth_service.is_person_allowed(None, "alice@example.com")

    def test_exact_domain_match(self):
        with (
            patch("core.config.ALLOWED_EMAILS", []),
            patch("core.config.ALLOWED_DOMAINS", ["example.com"]),
            patch("core.config.ALLOWED_GOOGLE_IDS", []),
        ):
            assert auth_service.is_person_allowed(None, "anyone@example.com")
            assert not auth_service.is_person_allowed(None, "anyone@other.com")

    def test_glob_email_pattern(self):
        with (
            patch("core.config.ALLOWED_EMAILS", ["*@corp.com"]),
            patch("core.config.ALLOWED_DOMAINS", []),
            patch("core.config.ALLOWED_GOOGLE_IDS", []),
        ):
            assert auth_service.is_person_allowed(None, "alice@corp.com")
            assert not auth_service.is_person_allowed(None, "bob@home.com")

    def test_google_id_match(self):
        with (
            patch("core.config.ALLOWED_EMAILS", []),
            patch("core.config.ALLOWED_DOMAINS", []),
            patch("core.config.ALLOWED_GOOGLE_IDS", ["12345"]),
        ):
            assert auth_service.is_person_allowed("12345", None)
            assert not auth_service.is_person_allowed("99999", None)

    def test_email_case_insensitive(self):
        with (
            patch("core.config.ALLOWED_EMAILS", ["bob@example.com"]),
            patch("core.config.ALLOWED_DOMAINS", []),
            patch("core.config.ALLOWED_GOOGLE_IDS", []),
        ):
            assert auth_service.is_person_allowed(None, "BOB@EXAMPLE.COM")
