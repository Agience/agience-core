"""Inbound-nonce verification tests (Mantle side).

The issuer (`issue_nonce`) lives on Origin alongside the rest of identity.
Mantle keeps `verify_nonce` for inbound API key challenge flows. These tests
build tokens with the same HMAC contract Origin uses, then exercise Mantle's
verification path.

The HTTP endpoint tests for `GET /auth/nonce` are now in `origin/tests/` —
that's where the route lives.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from services.auth_service import NONCE_TTL_SECONDS, verify_nonce


_SECRET = "test-nonce-secret-32-bytes-long!!"
_KEY_ID = "key-abc123"
_ARTIFACT_ID = "artifact-xyz789"


def _build_nonce(
    key_id: str,
    artifact_id: str,
    secret: str,
    *,
    ts: int | None = None,
) -> str:
    """Replicate Origin's `issue_nonce` HMAC token shape:
    ``b64({ts}:{artifact_id}:{key_id}:{sig})`` where
    ``sig = hmac_sha256(secret, "{ts}:{artifact_id}:{key_id}")``.
    """
    ts = int(time.time()) if ts is None else ts
    payload = f"{ts}:{artifact_id}:{key_id}"
    sig = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    raw = f"{ts}:{artifact_id}:{key_id}:{sig}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).rstrip(b"=").decode("utf-8")


# ---------------------------------------------------------------------------
# verify_nonce — pure unit tests (no HTTP, no DB)
# ---------------------------------------------------------------------------

def test_verify_nonce_valid():
    token = _build_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, _KEY_ID, _ARTIFACT_ID, _SECRET) is True


def test_verify_nonce_wrong_key_id():
    token = _build_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, "wrong-key", _ARTIFACT_ID, _SECRET) is False


def test_verify_nonce_wrong_artifact_id():
    token = _build_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, _KEY_ID, "wrong-artifact", _SECRET) is False


def test_verify_nonce_wrong_secret():
    token = _build_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, _KEY_ID, _ARTIFACT_ID, "other-secret") is False


def test_verify_nonce_expired():
    token = _build_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    # ttl_seconds=-1 means any token is immediately expired
    assert verify_nonce(token, _KEY_ID, _ARTIFACT_ID, _SECRET, ttl_seconds=-1) is False


def test_verify_nonce_old_token():
    # Token with ts well before now, default ttl
    old_ts = int(time.time()) - (NONCE_TTL_SECONDS + 60)
    token = _build_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET, ts=old_ts)
    assert verify_nonce(token, _KEY_ID, _ARTIFACT_ID, _SECRET) is False


def test_verify_nonce_tampered_token():
    assert verify_nonce("notavalidtoken", _KEY_ID, _ARTIFACT_ID, _SECRET) is False


def test_verify_nonce_empty_token():
    assert verify_nonce("", _KEY_ID, _ARTIFACT_ID, _SECRET) is False


def test_verify_nonce_no_secret():
    token = _build_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, _KEY_ID, _ARTIFACT_ID, "") is False
