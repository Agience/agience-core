"""Tests for core.service_identity — per-service signing identity."""
from __future__ import annotations

import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

from kernel import service_identity


@pytest.fixture(autouse=True)
def _reset_identity():
    """Each test starts with a clean module state."""
    service_identity.reset_service_identity_for_tests()
    yield
    service_identity.reset_service_identity_for_tests()


@pytest.fixture
def keys_dir(tmp_path, monkeypatch):
    """A temp KEYS_DIR with origin/mantle/chorus private keys written into it."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))
    for name in ("origin", "mantle", "chorus"):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        (tmp_path / f"{name}.private.pem").write_bytes(pem)
    return tmp_path


def test_init_loads_private_key(keys_dir):
    identity = service_identity.init_service_identity("origin")
    assert identity.name == "origin"
    assert identity.kid == "origin-1"
    assert isinstance(identity.private_key, rsa.RSAPrivateKey)


def test_get_returns_loaded_identity(keys_dir):
    service_identity.init_service_identity("mantle")
    identity = service_identity.get_service_identity()
    assert identity.name == "mantle"
    assert identity.kid == "mantle-1"


def test_get_without_init_raises():
    with pytest.raises(RuntimeError, match="not initialized"):
        service_identity.get_service_identity()


def test_init_idempotent_for_same_service(keys_dir):
    a = service_identity.init_service_identity("mantle")
    b = service_identity.init_service_identity("mantle")
    assert a is b


def test_init_replaces_when_service_changes(keys_dir):
    """Switching service name resets state. Useful in test contexts; production never does this."""
    service_identity.init_service_identity("origin")
    service_identity.reset_service_identity_for_tests()
    service_identity.init_service_identity("mantle")
    assert service_identity.get_service_identity().name == "mantle"


def test_init_rejects_unknown_service_name(keys_dir):
    with pytest.raises(ValueError, match="Unknown service name"):
        service_identity.init_service_identity("not-a-service")


def test_init_raises_if_key_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="Service private key missing"):
        service_identity.init_service_identity("origin")


def test_sign_service_jwt_default_claims(keys_dir):
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="mantle")

    # Decode without verification (we test verification in test_authority_trust).
    claims = jose_jwt.get_unverified_claims(token)
    headers = jose_jwt.get_unverified_header(token)

    assert claims["iss"] == "origin"
    assert claims["sub"] == "origin"
    assert claims["aud"] == "mantle"
    assert claims["principal_type"] == "service"
    assert "iat" in claims
    assert "exp" in claims
    assert claims["exp"] - claims["iat"] == service_identity.DEFAULT_TTL_SECONDS
    assert headers["kid"] == "origin-1"
    assert headers["alg"] == "RS256"


def test_sign_service_jwt_custom_ttl(keys_dir):
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="mantle", ttl_seconds=60)
    claims = jose_jwt.get_unverified_claims(token)
    assert claims["exp"] - claims["iat"] == 60


def test_sign_service_jwt_additional_claims_cannot_override_defaults(keys_dir):
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(
        audience="mantle",
        additional_claims={"iss": "evil", "principal_type": "evil", "scope": "read"},
    )
    claims = jose_jwt.get_unverified_claims(token)
    # Defaults preserved
    assert claims["iss"] == "origin"
    assert claims["principal_type"] == "service"
    # Genuinely new claim accepted
    assert claims["scope"] == "read"


def test_sign_service_jwt_issuer_override(keys_dir):
    """issuer_override is for narrow bootstrap cases."""
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(
        audience="mantle",
        issuer_override="https://platform.example.com",
    )
    claims = jose_jwt.get_unverified_claims(token)
    assert claims["iss"] == "https://platform.example.com"
    assert claims["sub"] == "origin"  # sub still records the service name


def test_sign_delegation_jwt_default_claims(keys_dir):
    service_identity.init_service_identity("mantle")
    token = service_identity.sign_delegation_jwt(
        audience="chorus",
        user_sub="user-uuid-123",
    )
    claims = jose_jwt.get_unverified_claims(token)
    assert claims["iss"] == "mantle"
    assert claims["sub"] == "user-uuid-123"
    assert claims["aud"] == "chorus"
    assert claims["principal_type"] == "delegation"
    assert claims["act"]["sub"] == "mantle"


def test_sign_delegation_jwt_default_ttl(keys_dir):
    service_identity.init_service_identity("mantle")
    before = int(time.time())
    token = service_identity.sign_delegation_jwt(audience="chorus", user_sub="u1")
    claims = jose_jwt.get_unverified_claims(token)
    assert claims["exp"] - claims["iat"] == service_identity.DEFAULT_DELEGATION_TTL_SECONDS
    assert claims["iat"] >= before


def test_sign_delegation_jwt_additional_claims(keys_dir):
    service_identity.init_service_identity("mantle")
    token = service_identity.sign_delegation_jwt(
        audience="chorus",
        user_sub="u1",
        additional_claims={"scope": "read", "act": {"sub": "evil"}},
    )
    claims = jose_jwt.get_unverified_claims(token)
    # Custom scope passes through; act.sub default wins
    assert claims["scope"] == "read"
    assert claims["act"]["sub"] == "mantle"


