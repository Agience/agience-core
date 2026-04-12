"""Tests for ``client_credentials`` grant type on ``POST /auth/token``.

Validates the server-to-platform authentication flow added by the
entity-identity-and-credentials spec.

Kernel (first-party) servers in KERNEL_SERVER_IDS authenticate with the
shared PLATFORM_INTERNAL_SECRET.  Third-party servers use provisioned
ServerCredential records (DB-backed bcrypt check).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import bcrypt
import pytest

_RAW_SECRET = "scs_testrawsecretvalue"
_SECRET_HASH = bcrypt.hashpw(_RAW_SECRET.encode(), bcrypt.gensalt()).decode()

# Use a non-kernel client_id so the provisioned-credential code path executes.
# Kernel server IDs ("agience-server-aria", etc.) take the fast-path that
# validates against PLATFORM_INTERNAL_SECRET instead of the DB.
_THIRD_PARTY_CLIENT_ID = "my-custom-server"


@dataclass
class ServerCredentialStub:
    id: str = "cred-1"
    client_id: str = _THIRD_PARTY_CLIENT_ID
    name: str = "MyCustomServer"
    secret_hash: str = _SECRET_HASH
    authority: str = "my.agience.ai"
    host_id: str = "host-1"
    server_id: str = "server-1"
    scopes: List[str] = field(default_factory=lambda: ["resource:*:*"])
    resource_filters: Dict[str, Any] = field(default_factory=dict)
    user_id: str = "user-123"
    is_active: bool = True
    created_time: str = "2025-01-01T00:00:00+00:00"
    modified_time: str = "2025-01-01T00:00:00+00:00"
    last_used_at: Optional[str] = None
    last_rotated_at: Optional[str] = None


class TestClientCredentialsGrant:

    @pytest.mark.asyncio
    @patch("routers.auth_router.create_jwt_token", return_value="mock.jwt.token")
    @patch("routers.auth_router.db_update_cred_last_used")
    @patch("routers.auth_router.db_get_server_credential")
    async def test_happy_path(self, mock_get_cred, mock_update, _mock_jwt, client):
        mock_get_cred.return_value = ServerCredentialStub()
        mock_update.return_value = None

        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": _THIRD_PARTY_CLIENT_ID,
                "client_secret": _RAW_SECRET,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 3600
        # No refresh token for client_credentials
        assert "refresh_token" not in data

        # last_used_at should be updated
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.auth_router.db_get_server_credential")
    async def test_unknown_client_id(self, mock_get_cred, client):
        mock_get_cred.return_value = None

        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "unknown-server",
                "client_secret": "scs_whatever",
            },
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"] == "invalid_client"

    @pytest.mark.asyncio
    @patch("routers.auth_router.db_get_server_credential")
    async def test_inactive_credential(self, mock_get_cred, client):
        mock_get_cred.return_value = ServerCredentialStub(is_active=False)

        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": _THIRD_PARTY_CLIENT_ID,
                "client_secret": _RAW_SECRET,
            },
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_client"

    @pytest.mark.asyncio
    @patch("routers.auth_router.db_get_server_credential")
    async def test_wrong_secret(self, mock_get_cred, client):
        mock_get_cred.return_value = ServerCredentialStub()

        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": _THIRD_PARTY_CLIENT_ID,
                "client_secret": "scs_wrongsecret",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_client"

    @pytest.mark.asyncio
    async def test_missing_client_secret(self, client):
        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": _THIRD_PARTY_CLIENT_ID,
                # no client_secret
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_unsupported_grant_type(self, client):
        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "password",
                "client_id": "whatever",
            },
        )
        assert resp.status_code == 400


class TestKernelServerAuth:
    """Kernel servers authenticate with PLATFORM_INTERNAL_SECRET, bypassing DB."""

    _KERNEL_CLIENT_ID = "agience-server-aria"  # In KERNEL_SERVER_IDS
    _KERNEL_SECRET = "test-platform-internal-secret"

    @pytest.mark.asyncio
    @patch("routers.auth_router.create_jwt_token", return_value="kernel.jwt.token")
    @patch("core.config.PLATFORM_INTERNAL_SECRET", _KERNEL_SECRET)
    async def test_kernel_happy_path(self, _mock_jwt, client):
        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._KERNEL_CLIENT_ID,
                "client_secret": self._KERNEL_SECRET,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "kernel.jwt.token"
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 3600

    @pytest.mark.asyncio
    @patch("core.config.PLATFORM_INTERNAL_SECRET", _KERNEL_SECRET)
    async def test_kernel_wrong_secret(self, client):
        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._KERNEL_CLIENT_ID,
                "client_secret": "wrong-secret",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_client"

    @pytest.mark.asyncio
    @patch("core.config.PLATFORM_INTERNAL_SECRET", None)
    async def test_kernel_secret_not_configured(self, client):
        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._KERNEL_CLIENT_ID,
                "client_secret": "any-secret",
            },
        )
        assert resp.status_code == 503
        assert "not configured" in resp.json()["error_description"]
