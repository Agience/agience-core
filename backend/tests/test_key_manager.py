"""
tests/test_key_manager.py

Tests for key_manager read-only behavior.
The backend no longer generates keys — the init container generates them
before the backend starts. These tests verify that:
  - init_licensing_keys loads Ed25519 keys from pre-existing files
  - init_licensing_keys raises RuntimeError when key files are absent
  - init_jwt_keys raises RuntimeError when key files are absent
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from core import key_manager


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _generate_ed25519_key_files(tmp_path):
    """Write an Ed25519 key pair to tmp_path for test fixtures."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_path = tmp_path / "licensing_private.pem"
    pub_path = tmp_path / "licensing_public.pem"

    priv_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return priv_path, pub_path


# ---------------------------------------------------------------------------
#  init_licensing_keys — happy path
# ---------------------------------------------------------------------------

def test_init_licensing_keys_loads_existing_keypair(tmp_path):
    """init_licensing_keys should load valid Ed25519 key files without error."""
    priv_path, pub_path = _generate_ed25519_key_files(tmp_path)
    trust_anchors_path = tmp_path / "licensing_trust_anchors.json"

    # Should not raise
    key_manager.init_licensing_keys(
        private_key_path=priv_path,
        public_key_path=pub_path,
        trust_anchors_path=trust_anchors_path,
        key_id="lic-test",
    )

    # Paths should be recorded in module state
    assert key_manager.get_licensing_private_key_path() == priv_path
    assert key_manager.get_licensing_public_key_path() == pub_path
    assert key_manager.get_licensing_key_id() == "lic-test"


# ---------------------------------------------------------------------------
#  init_licensing_keys — error cases
# ---------------------------------------------------------------------------

def test_init_licensing_keys_raises_when_files_missing(tmp_path):
    """init_licensing_keys must raise RuntimeError when key files are absent."""
    with pytest.raises(RuntimeError, match="Licensing key files not found"):
        key_manager.init_licensing_keys(
            private_key_path=tmp_path / "missing_private.pem",
            public_key_path=tmp_path / "missing_public.pem",
            trust_anchors_path=tmp_path / "trust.json",
            key_id="lic-test",
        )


def test_init_licensing_keys_raises_when_private_key_missing(tmp_path):
    """Raising also when only the private key is missing."""
    _, pub_path = _generate_ed25519_key_files(tmp_path)
    with pytest.raises(RuntimeError, match="Licensing key files not found"):
        key_manager.init_licensing_keys(
            private_key_path=tmp_path / "missing_private.pem",
            public_key_path=pub_path,
            trust_anchors_path=tmp_path / "trust.json",
            key_id="lic-test",
        )


# ---------------------------------------------------------------------------
#  init_jwt_keys — error case
# ---------------------------------------------------------------------------

def test_init_jwt_keys_raises_when_files_missing(tmp_path):
    """init_jwt_keys must raise RuntimeError when JWT key files are absent."""
    with pytest.raises(RuntimeError, match="JWT key files not found"):
        key_manager.init_jwt_keys(
            private_key_path=tmp_path / "missing_jwt_private.pem",
            public_key_path=tmp_path / "missing_jwt_public.pem",
        )
