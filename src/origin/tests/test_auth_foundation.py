"""Tests for the 1.1a-i Origin auth foundation (no router wired yet).

Covers:
- JWT issuance + verification roundtrip
- Password hash + verify
- Nonce issue + verify
- API key generation
- Allow-list (`is_person_allowed`)
- Redirect URI gate (`is_client_redirect_allowed`)
- AuthContext shape parity with Mantle
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def auth_modules(monkeypatch, jwt_keypair):
    """Initialize JWT keys and return the freshly-loaded auth modules."""
    monkeypatch.setenv("KEYS_DIR", str(jwt_keypair))
    monkeypatch.setenv("ORIGIN_SKIP_MIGRATIONS", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    import kernel.config as cfg
    import kernel.key_manager as km

    importlib.reload(cfg)
    importlib.reload(km)
    km.init_jwt_keys()

    from origin.services import auth_service, auth_verifier
    from origin.services import dependencies as origin_deps

    importlib.reload(auth_service)
    importlib.reload(auth_verifier)
    importlib.reload(origin_deps)

    return {
        "config": cfg,
        "auth_service": auth_service,
        "auth_verifier": auth_verifier,
        "deps": origin_deps,
    }


def test_jwt_issue_and_verify_roundtrip(auth_modules):
    cfg = auth_modules["config"]
    issuance = auth_modules["auth_service"]
    verify = auth_modules["auth_verifier"]

    token = issuance.create_jwt_token(
        {"sub": "user-1", "aud": cfg.AUTHORITY_ISSUER, "principal_type": "user"}
    )
    payload = verify.verify_token(token, expected_audience=cfg.AUTHORITY_ISSUER)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["principal_type"] == "user"


def test_jwt_rejects_wrong_audience(auth_modules):
    cfg = auth_modules["config"]
    issuance = auth_modules["auth_service"]
    verify = auth_modules["auth_verifier"]

    token = issuance.create_jwt_token({"sub": "user-1", "aud": cfg.AUTHORITY_ISSUER})
    assert verify.verify_token(token, expected_audience="not-the-issuer") is None


def test_password_roundtrip(auth_modules):
    auth_service = auth_modules["auth_service"]
    h = auth_service.hash_password("correct horse battery staple")
    assert auth_service.verify_password("correct horse battery staple", h)
    assert not auth_service.verify_password("wrong password", h)
    assert not auth_service.verify_password("", h)


def test_password_rejects_malformed_hash(auth_modules):
    auth_service = auth_modules["auth_service"]
    assert not auth_service.verify_password("any", "not-a-valid-hash")


def test_nonce_roundtrip(auth_modules):
    issuance = auth_modules["auth_service"]
    verify = auth_modules["auth_verifier"]

    token, _exp = issuance.issue_nonce(key_id="k1", artifact_id="a1", secret="s")
    assert verify.verify_nonce(token, "k1", "a1", "s")
    # Mismatched binding
    assert not verify.verify_nonce(token, "k1", "a2", "s")
    assert not verify.verify_nonce(token, "k2", "a1", "s")
    # Wrong secret
    assert not verify.verify_nonce(token, "k1", "a1", "different-secret")


def test_api_key_format(auth_modules):
    auth_service = auth_modules["auth_service"]
    k = auth_service.generate_api_key()
    assert k.startswith("agc_")
    assert len(k) == len("agc_") + 32  # 16 bytes hex
    assert len(auth_service.hash_api_key(k)) == 64  # sha256 hex


def test_is_person_allowed_default_allow(auth_modules):
    cfg = auth_modules["config"]
    auth_service = auth_modules["auth_service"]
    cfg.ALLOWED_EMAILS = []
    cfg.ALLOWED_DOMAINS = []
    cfg.ALLOWED_GOOGLE_IDS = []
    assert auth_service.is_person_allowed(None, "anyone@example.com")


def test_is_person_allowed_domain_match(auth_modules):
    cfg = auth_modules["config"]
    auth_service = auth_modules["auth_service"]
    cfg.ALLOWED_EMAILS = []
    cfg.ALLOWED_DOMAINS = ["example.com"]
    cfg.ALLOWED_GOOGLE_IDS = []
    assert auth_service.is_person_allowed(None, "a@example.com")
    assert not auth_service.is_person_allowed(None, "a@evil.com")


def test_is_person_allowed_glob_pattern(auth_modules):
    cfg = auth_modules["config"]
    auth_service = auth_modules["auth_service"]
    cfg.ALLOWED_EMAILS = []
    cfg.ALLOWED_DOMAINS = ["*.example.com"]
    cfg.ALLOWED_GOOGLE_IDS = []
    assert auth_service.is_person_allowed(None, "user@team.example.com")
    assert not auth_service.is_person_allowed(None, "user@example.com")  # bare domain doesn't match *.x


def test_is_client_redirect_allowed(auth_modules):
    cfg = auth_modules["config"]
    auth_service = auth_modules["auth_service"]
    cfg.FACET_URI = "http://localhost:5173"
    cfg.ORIGIN_URI = "http://localhost:8081"

    assert auth_service.is_client_redirect_allowed("http://localhost:5173/callback")
    assert auth_service.is_client_redirect_allowed("http://localhost:8081/callback")
    assert auth_service.is_client_redirect_allowed("https://vscodeinternal design notes")
    assert auth_service.is_client_redirect_allowed("http://127.0.0.1:9000/cb")
    assert not auth_service.is_client_redirect_allowed("http://evil.example/cb")
    assert not auth_service.is_client_redirect_allowed("ftp://localhost:5173/")


def test_authcontext_field_parity(auth_modules):
    """AuthContext fields must match Mantle's shape so router code is portable."""
    deps = auth_modules["deps"]
    ctx = deps.AuthContext()
    expected = {
        "principal_id",
        "principal_type",
        "user_id",
        "grants",
        "api_key_id",
        "api_key_entity",
        "server_id",
        "actor",
        "authority",
        "host_id",
        "bearer_grant",
        "target_artifact_id",
    }
    actual = set(ctx.__dataclass_fields__.keys())
    assert actual == expected, f"AuthContext shape drift: {actual ^ expected}"


def test_db_modules_import_cleanly():
    """Smoke check: all Origin DB CRUD modules import without errors."""
    from origin.db import api_keys, grants, persons, platform_settings, server_credentials  # noqa: F401
