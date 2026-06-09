"""Tests for core.authority_trust — authority manifest loading + JWT verification."""
from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose.exceptions import JWTError

from kernel import authority_trust, service_identity


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _public_jwk(public_key, kid: str) -> dict:
    nums = public_key.public_numbers()
    n = nums.n.to_bytes((nums.n.bit_length() + 7) // 8, "big")
    e = nums.e.to_bytes((nums.e.bit_length() + 7) // 8, "big")
    return {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": kid,
        "n": _b64url(n),
        "e": _b64url(e),
    }


@pytest.fixture(autouse=True)
def _reset():
    authority_trust.reset_authority_manifest_for_tests()
    service_identity.reset_service_identity_for_tests()
    yield
    authority_trust.reset_authority_manifest_for_tests()
    service_identity.reset_service_identity_for_tests()


@pytest.fixture
def trust_setup(tmp_path, monkeypatch):
    """A temp KEYS_DIR with three keypairs and a matching authority manifest.

    Returns a dict { service_name -> RSAPrivateKey } so tests can sign tokens
    they then ask authority_trust to verify.
    """
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))

    keys: dict = {}
    trust_anchors: dict = {}

    for name in ("origin", "mantle", "chorus"):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        (tmp_path / f"{name}.private.pem").write_bytes(priv_pem)
        keys[name] = key
        trust_anchors[name] = {
            "uri": f"http://{name}:8080",
            "jwks": {"keys": [_public_jwk(key.public_key(), f"{name}-1")]},
        }

    manifest = {
        "artifact_id": "test-authority-id",
        "content_type": "application/vnd.agience.authority+json",
        "schema_version": 1,
        "issuer": "https://platform.test",
        "trust_anchors": trust_anchors,
        "bootstrap_token_hash": "abc123",
    }
    (tmp_path / "authority.manifest.json").write_text(json.dumps(manifest, indent=2))
    return {"keys": keys, "manifest": manifest, "tmp_path": tmp_path}


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def test_load_manifest_parses_fields(trust_setup):
    manifest = authority_trust.load_authority_manifest()
    assert manifest.issuer == "https://platform.test"
    assert manifest.artifact_id == "test-authority-id"
    assert manifest.bootstrap_token_hash == "abc123"
    assert set(manifest.trust_anchors.keys()) == {"origin", "mantle", "chorus"}


def test_load_manifest_caches_result(trust_setup):
    a = authority_trust.load_authority_manifest()
    b = authority_trust.load_authority_manifest()
    assert a is b


def test_get_returns_cached_manifest(trust_setup):
    a = authority_trust.load_authority_manifest()
    b = authority_trust.get_authority_manifest()
    assert a is b


def test_reload_rereads_from_disk(trust_setup):
    a = authority_trust.load_authority_manifest()
    # Mutate the on-disk manifest
    raw = a.raw.copy()
    raw["bootstrap_token_hash"] = None  # operator claimed it
    (trust_setup["tmp_path"] / "authority.manifest.json").write_text(json.dumps(raw))

    # Without reload, still cached value
    assert authority_trust.get_authority_manifest().bootstrap_token_hash == "abc123"

    # After reload, picks up the change
    fresh = authority_trust.reload_authority_manifest()
    assert fresh.bootstrap_token_hash is None


def test_load_raises_if_manifest_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="Authority manifest missing"):
        authority_trust.load_authority_manifest()


def test_get_jwks_returns_inline_keys(trust_setup):
    manifest = authority_trust.load_authority_manifest()
    jwks = manifest.get_jwks("origin")
    assert "keys" in jwks
    assert jwks["keys"][0]["kid"] == "origin-1"


def test_get_jwks_unknown_service_raises(trust_setup):
    manifest = authority_trust.load_authority_manifest()
    with pytest.raises(KeyError, match="No trust anchor"):
        manifest.get_jwks("unknown-service")


def test_get_uri(trust_setup):
    manifest = authority_trust.load_authority_manifest()
    assert manifest.get_uri("origin") == "http://origin:8080"
    assert manifest.get_uri("missing") is None


# ---------------------------------------------------------------------------
# verify_service_jwt
# ---------------------------------------------------------------------------


def test_verify_service_jwt_accepts_valid_token(trust_setup):
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="mantle")

    claims = authority_trust.verify_service_jwt(
        token, expected_issuer="origin", expected_audience="mantle"
    )
    assert claims["iss"] == "origin"
    assert claims["aud"] == "mantle"
    assert claims["principal_type"] == "service"


def test_verify_service_jwt_rejects_wrong_audience(trust_setup):
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="mantle")

    with pytest.raises(JWTError):
        authority_trust.verify_service_jwt(
            token, expected_issuer="origin", expected_audience="chorus"
        )


def test_verify_service_jwt_rejects_wrong_issuer(trust_setup):
    """A token signed by origin cannot be verified as mantle-issued —
    its signature won't match mantle's public key."""
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="mantle")

    with pytest.raises(JWTError):
        authority_trust.verify_service_jwt(
            token, expected_issuer="mantle", expected_audience="mantle"
        )


def test_verify_service_jwt_rejects_expired_token(trust_setup):
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="mantle", ttl_seconds=-1)
    # Even a one-second skew margin doesn't save us — token is already past exp.
    with pytest.raises(JWTError):
        authority_trust.verify_service_jwt(
            token, expected_issuer="origin", expected_audience="mantle"
        )


def test_verify_service_jwt_rejects_tampered_signature(trust_setup):
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="mantle")
    # Flip a byte in the signature (last segment of the JWT)
    head, payload, sig = token.split(".")
    tampered_sig = sig[:-2] + ("AB" if sig[-2:] != "AB" else "CD")
    bad_token = f"{head}.{payload}.{tampered_sig}"

    with pytest.raises(JWTError):
        authority_trust.verify_service_jwt(
            bad_token, expected_issuer="origin", expected_audience="mantle"
        )


def test_verify_service_jwt_rejects_when_anchor_missing(trust_setup):
    """If the manifest lacks an anchor for the claimed issuer, verification fails fast."""
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="mantle")

    # Drop origin from the manifest and force reload
    raw = json.loads(
        (trust_setup["tmp_path"] / "authority.manifest.json").read_text()
    )
    del raw["trust_anchors"]["origin"]
    (trust_setup["tmp_path"] / "authority.manifest.json").write_text(json.dumps(raw))
    authority_trust.reload_authority_manifest()

    with pytest.raises(KeyError, match="No trust anchor"):
        authority_trust.verify_service_jwt(
            token, expected_issuer="origin", expected_audience="mantle"
        )


# ---------------------------------------------------------------------------
# verify_delegation_jwt
# ---------------------------------------------------------------------------


def test_verify_delegation_jwt_accepts_valid_token(trust_setup):
    service_identity.init_service_identity("mantle")
    token = service_identity.sign_delegation_jwt(
        audience="chorus", user_sub="user-123"
    )

    claims = authority_trust.verify_delegation_jwt(
        token,
        expected_issuer="mantle",
        expected_audience="chorus",
        expected_actor="mantle",
    )
    assert claims["sub"] == "user-123"
    assert claims["principal_type"] == "delegation"
    assert claims["act"]["sub"] == "mantle"


def test_verify_delegation_jwt_rejects_service_token(trust_setup):
    """A `principal_type=service` token must NOT pass delegation verification."""
    service_identity.init_service_identity("mantle")
    token = service_identity.sign_service_jwt(audience="chorus")

    with pytest.raises(JWTError, match="principal_type"):
        authority_trust.verify_delegation_jwt(
            token, expected_issuer="mantle", expected_audience="chorus"
        )


def test_verify_delegation_jwt_rejects_wrong_actor(trust_setup):
    """If the verifier expects a specific actor, a different one is rejected."""
    service_identity.init_service_identity("mantle")
    token = service_identity.sign_delegation_jwt(audience="chorus", user_sub="u1")

    with pytest.raises(JWTError, match="act.sub"):
        authority_trust.verify_delegation_jwt(
            token,
            expected_issuer="mantle",
            expected_audience="chorus",
            expected_actor="origin",
        )


def test_verify_delegation_jwt_actor_check_optional(trust_setup):
    """Omitting expected_actor skips the actor check (still validates type/sig/aud/iss)."""
    service_identity.init_service_identity("mantle")
    token = service_identity.sign_delegation_jwt(audience="chorus", user_sub="u1")

    claims = authority_trust.verify_delegation_jwt(
        token, expected_issuer="mantle", expected_audience="chorus"
    )
    assert claims["sub"] == "u1"


# ---------------------------------------------------------------------------
# verify_jwt (lower-level, audience-flexible)
# ---------------------------------------------------------------------------


def test_verify_jwt_skips_audience_when_unset(trust_setup):
    """User tokens have variable audience (per-OAuth-client). Skipping aud check is supported."""
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(
        audience="https://platform.test",
        additional_claims={"sub": "user-123"},
    )
    # Caller doesn't pass expected_audience — verifier should skip aud check.
    claims = authority_trust.verify_jwt(token, expected_issuer_service="origin")
    assert claims["aud"] == "https://platform.test"


def test_verify_jwt_skips_issuer_claim_when_unset(trust_setup):
    """User tokens have iss = platform URL, not service name. Skip iss check."""
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(
        audience="some-client",
        issuer_override="https://platform.test",
    )
    # Token's `iss` claim is the URL, not "origin" — caller skips iss check.
    claims = authority_trust.verify_jwt(
        token,
        expected_issuer_service="origin",
        expected_audience="some-client",
    )
    assert claims["iss"] == "https://platform.test"


def test_verify_jwt_accepts_audience_list(trust_setup):
    """Multiple acceptable audiences (e.g. 'agience' OR a specific client_id)."""
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="agience")
    claims = authority_trust.verify_jwt(
        token,
        expected_issuer_service="origin",
        expected_audience=["agience", "other-client"],
    )
    assert claims["aud"] == "agience"


def test_verify_jwt_rejects_unmatched_audience_list(trust_setup):
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="agience")
    with pytest.raises(JWTError):
        authority_trust.verify_jwt(
            token,
            expected_issuer_service="origin",
            expected_audience=["other-1", "other-2"],
        )


def test_verify_jwt_signature_check_always_runs(trust_setup):
    """Even with all claim checks disabled, signature must still be valid."""
    service_identity.init_service_identity("origin")
    token = service_identity.sign_service_jwt(audience="anything")
    head, payload, sig = token.split(".")
    bad = f"{head}.{payload}.{sig[:-2]}AB"
    with pytest.raises(JWTError):
        authority_trust.verify_jwt(bad, expected_issuer_service="origin")

