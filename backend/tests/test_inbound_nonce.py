# tests/test_inbound_nonce.py
#
# Unit tests for inbound nonce issuance and verification.
# Covers: issue_nonce / verify_nonce helpers and GET /auth/nonce endpoint.

import time
import pytest
from unittest.mock import patch
from httpx import AsyncClient

from services.auth_service import issue_nonce, verify_nonce, NONCE_TTL_SECONDS
from entities.api_key import APIKey as APIKeyEntity

_SECRET = "test-nonce-secret-32-bytes-long!!"
_KEY_ID = "key-abc123"
_ARTIFACT_ID = "artifact-xyz789"


# ---------------------------------------------------------------------------
# issue_nonce / verify_nonce — pure unit tests (no HTTP, no DB)
# ---------------------------------------------------------------------------

def test_issue_nonce_returns_token_and_expiry():
    token, expires_at = issue_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert token
    assert expires_at is not None


def test_verify_nonce_valid():
    token, _ = issue_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, _KEY_ID, _ARTIFACT_ID, _SECRET) is True


def test_verify_nonce_wrong_key_id():
    token, _ = issue_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, "wrong-key", _ARTIFACT_ID, _SECRET) is False


def test_verify_nonce_wrong_artifact_id():
    token, _ = issue_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, _KEY_ID, "wrong-artifact", _SECRET) is False


def test_verify_nonce_wrong_secret():
    token, _ = issue_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, _KEY_ID, _ARTIFACT_ID, "other-secret") is False


def test_verify_nonce_expired():
    token, _ = issue_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    # ttl_seconds=-1 means any token is immediately expired
    assert verify_nonce(token, _KEY_ID, _ARTIFACT_ID, _SECRET, ttl_seconds=-1) is False


def test_verify_nonce_tampered_token():
    assert verify_nonce("notavalidtoken", _KEY_ID, _ARTIFACT_ID, _SECRET) is False


def test_verify_nonce_empty_token():
    assert verify_nonce("", _KEY_ID, _ARTIFACT_ID, _SECRET) is False


def test_verify_nonce_no_secret():
    token, _ = issue_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    assert verify_nonce(token, _KEY_ID, _ARTIFACT_ID, "") is False


def test_issue_nonce_no_secret_raises():
    with pytest.raises(ValueError, match="INBOUND_NONCE_SECRET"):
        issue_nonce(_KEY_ID, _ARTIFACT_ID, "")


def test_nonce_expiry_timestamp():
    before = int(time.time())
    _, expires_at = issue_nonce(_KEY_ID, _ARTIFACT_ID, _SECRET)
    after = int(time.time())
    ts = int(expires_at.timestamp())
    assert before + NONCE_TTL_SECONDS <= ts <= after + NONCE_TTL_SECONDS + 1


# ---------------------------------------------------------------------------
# GET /auth/nonce — HTTP endpoint tests
# ---------------------------------------------------------------------------

def _inbound_key_entity(key_id: str = _KEY_ID) -> APIKeyEntity:
    k = APIKeyEntity(id=key_id, user_id="user-1", requires_nonce=True)
    return k


def _regular_key_entity(key_id: str = "regular-key") -> APIKeyEntity:
    k = APIKeyEntity(id=key_id, user_id="user-1")
    return k


@pytest.mark.asyncio
async def test_issue_challenge_nonce_returns_token(client: AsyncClient):
    from services.dependencies import AuthContext

    inbound_key = _inbound_key_entity()
    auth_ctx = AuthContext(
        principal_id=_KEY_ID,
        principal_type="api_key",
        api_key_id=_KEY_ID,
        api_key_entity=inbound_key,
        target_artifact_id=_ARTIFACT_ID,
    )

    from main import app
    from services.dependencies import get_auth

    app.dependency_overrides[get_auth] = lambda: auth_ctx

    with patch("routers.auth_router.config") as mock_config:
        mock_config.INBOUND_NONCE_SECRET = _SECRET
        resp = await client.get("/auth/nonce")

    app.dependency_overrides.pop(get_auth, None)

    assert resp.status_code == 200
    data = resp.json()
    assert "nonce" in data
    assert "expires_at" in data
    # Verify the returned nonce is actually valid
    assert verify_nonce(data["nonce"], _KEY_ID, _ARTIFACT_ID, _SECRET) is True


@pytest.mark.asyncio
async def test_issue_challenge_nonce_rejects_non_inbound_key(client: AsyncClient):
    from services.dependencies import AuthContext

    regular_key = _regular_key_entity()
    auth_ctx = AuthContext(
        principal_id="regular-key",
        principal_type="api_key",
        api_key_id="regular-key",
        api_key_entity=regular_key,
        target_artifact_id=_ARTIFACT_ID,
    )

    from main import app
    from services.dependencies import get_auth

    app.dependency_overrides[get_auth] = lambda: auth_ctx

    resp = await client.get("/auth/nonce")
    app.dependency_overrides.pop(get_auth, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_issue_challenge_nonce_rejects_user_jwt(client: AsyncClient):
    from services.dependencies import AuthContext

    auth_ctx = AuthContext(
        principal_id="user-1",
        principal_type="user",
        user_id="user-1",
    )

    from main import app
    from services.dependencies import get_auth

    app.dependency_overrides[get_auth] = lambda: auth_ctx

    resp = await client.get("/auth/nonce")
    app.dependency_overrides.pop(get_auth, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_issue_challenge_nonce_503_when_secret_not_configured(client: AsyncClient):
    from services.dependencies import AuthContext

    inbound_key = _inbound_key_entity()
    auth_ctx = AuthContext(
        principal_id=_KEY_ID,
        principal_type="api_key",
        api_key_id=_KEY_ID,
        api_key_entity=inbound_key,
        target_artifact_id=_ARTIFACT_ID,
    )

    from main import app
    from services.dependencies import get_auth

    app.dependency_overrides[get_auth] = lambda: auth_ctx

    with patch("routers.auth_router.config") as mock_config:
        mock_config.INBOUND_NONCE_SECRET = ""
        resp = await client.get("/auth/nonce")

    app.dependency_overrides.pop(get_auth, None)

    assert resp.status_code == 503
