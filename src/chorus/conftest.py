"""Chorus-wide pytest fixtures.

Persona tools sign outbound JWTs via ``kernel.service_identity.sign_service_jwt``.
That module raises if no service identity has been loaded — normally the
chorus host's lifespan calls ``init_service_identity("chorus")`` after the
init container has written ``chorus.private.pem`` and the authority manifest.

Tests don't run the lifespan, so we materialize a throwaway chorus keypair
+ minimal authority manifest in a tmp dir and initialize service identity
once for the whole test session. Cleanup restores the original KEYS_DIR so
later test files (e.g. mantle's authority-content tests) don't see chorus's
fake manifest.
"""
from __future__ import annotations

import json
import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk


@pytest.fixture(scope="session", autouse=True)
def _chorus_test_identity(tmp_path_factory):
    keys_dir = tmp_path_factory.mktemp("chorus_keys")

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (keys_dir / "chorus.private.pem").write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    public_jwk = jwk.construct(public_pem, "RS256").to_dict()
    public_jwk["kid"] = "chorus-1"
    public_jwk["use"] = "sig"
    public_jwk["alg"] = "RS256"

    # Match the kernel default issuer so any cross-suite test that compares
    # `manifest.issuer` against `config.AUTHORITY_ISSUER` keeps working.
    from kernel import config as _cfg

    manifest = {
        "artifact_id": "00000000-0000-0000-0000-000000000001",
        "content_type": "application/vnd.agience.authority+json",
        "schema_version": 1,
        "issuer": _cfg.AUTHORITY_ISSUER,
        "trust_anchors": {
            "chorus": {"uri": "http://chorus.test", "jwks": {"keys": [public_jwk]}},
        },
    }
    (keys_dir / "authority.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    prior_keys_dir = os.environ.get("KEYS_DIR")
    os.environ["KEYS_DIR"] = str(keys_dir)

    from kernel import authority_trust as _at, service_identity as _si

    _si.reset_service_identity_for_tests()
    _at.reset_authority_manifest_for_tests()
    _si.init_service_identity("chorus")
    _at.load_authority_manifest()

    try:
        yield keys_dir
    finally:
        # Restore env + reset singletons so later test files start clean.
        if prior_keys_dir is None:
            os.environ.pop("KEYS_DIR", None)
        else:
            os.environ["KEYS_DIR"] = prior_keys_dir
        _si.reset_service_identity_for_tests()
        _at.reset_authority_manifest_for_tests()

