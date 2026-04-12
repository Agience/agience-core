"""Tests for routers/passkey_router.py — WebAuthn passkey ceremony.

Heavy crypto verification is delegated to py_webauthn (covered indirectly in
test_passkey_service.py). These tests verify the HTTP layer:
  - register-options requires a known user
  - register-options returns service options
  - register-complete decodes challenge and stores credential
  - login-options returns has_passkeys=False for users with no passkeys
  - login-options returns options when user has passkeys
  - login-complete 401 when verify_authentication fails
  - login-complete happy path returns JWT tokens
  - list/delete credential management endpoints
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient


class TestRegisterOptions:
    @pytest.mark.asyncio
    async def test_404_when_person_unknown(self, client: AsyncClient):
        with patch("db.arango_identity.get_person_by_id", return_value=None):
            r = await client.post("/auth/passkey/register-options")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_options_for_known_user(self, client: AsyncClient):
        with (
            patch(
                "db.arango_identity.get_person_by_id",
                return_value={"id": "user-123", "email": "u@e.com"},
            ),
            patch(
                "services.passkey_service.get_registration_options",
                return_value={"challenge": "abc", "rp": {"id": "x"}},
            ),
        ):
            r = await client.post("/auth/passkey/register-options")
        assert r.status_code == 200
        assert r.json()["options"]["challenge"] == "abc"


class TestRegisterComplete:
    @pytest.mark.asyncio
    async def test_stores_credential(self, client: AsyncClient):
        with patch(
            "services.passkey_service.verify_registration",
            return_value={"credential_id": "cred-1", "device_name": "YubiKey"},
        ) as svc:
            r = await client.post(
                "/auth/passkey/register-complete",
                json={
                    "credential": {"id": "x", "response": {}},
                    "device_name": "YubiKey",
                    "challenge": "YWJj",  # base64url "abc"
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["credential_id"] == "cred-1"
        assert body["device_name"] == "YubiKey"
        # The challenge was decoded from base64url before being passed to the service.
        assert svc.call_args.kwargs["expected_challenge"] == b"abc"


class TestLoginOptions:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_passkeys(self, client: AsyncClient):
        with patch("services.passkey_service.has_passkeys", return_value=False):
            r = await client.post(
                "/auth/passkey/login-options", json={"email": "u@e.com"}
            )
        assert r.status_code == 200
        body = r.json()
        assert body["has_passkeys"] is False
        assert body["options"] is None

    @pytest.mark.asyncio
    async def test_returns_options_when_user_has_passkeys(self, client: AsyncClient):
        with (
            patch("services.passkey_service.has_passkeys", return_value=True),
            patch(
                "services.passkey_service.get_authentication_options",
                return_value={
                    "challenge": "abc",
                    "rpId": "x",
                    "_user_id": "user-1",
                },
            ),
        ):
            r = await client.post(
                "/auth/passkey/login-options", json={"email": "u@e.com"}
            )
        assert r.status_code == 200
        body = r.json()
        assert body["has_passkeys"] is True
        assert body["options"]["challenge"] == "abc"


class TestLoginComplete:
    @pytest.mark.asyncio
    async def test_401_when_verification_fails(self, client: AsyncClient):
        with patch(
            "services.passkey_service.verify_authentication", return_value=None
        ):
            r = await client.post(
                "/auth/passkey/login-complete",
                json={
                    "credential": {"id": "x"},
                    "challenge": "YWJj",
                    "user_id": "user-1",
                },
            )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_401_when_person_record_missing(self, client: AsyncClient):
        with (
            patch(
                "services.passkey_service.verify_authentication",
                return_value="user-1",
            ),
            patch("db.arango_identity.get_person_by_id", return_value=None),
        ):
            r = await client.post(
                "/auth/passkey/login-complete",
                json={
                    "credential": {"id": "x"},
                    "challenge": "YWJj",
                    "user_id": "user-1",
                },
            )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_happy_path_returns_tokens(self, client: AsyncClient):
        person = {
            "id": "user-1",
            "email": "u@e.com",
            "name": "User",
            "picture": "",
        }
        with (
            patch(
                "services.passkey_service.verify_authentication",
                return_value="user-1",
            ),
            patch("db.arango_identity.get_person_by_id", return_value=person),
        ):
            r = await client.post(
                "/auth/passkey/login-complete",
                json={
                    "credential": {"id": "x"},
                    "challenge": "YWJj",
                    "user_id": "user-1",
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "bearer"


class TestCredentialManagement:
    @pytest.mark.asyncio
    async def test_list_returns_user_credentials(self, client: AsyncClient):
        with patch(
            "services.passkey_service.list_credentials",
            return_value=[
                {"credential_id": "c-1", "device_name": "YubiKey", "created_at": "t0", "last_used_at": None}
            ],
        ):
            r = await client.get("/auth/passkey/credentials")
        assert r.status_code == 200
        body = r.json()
        assert len(body["credentials"]) == 1
        assert body["credentials"][0]["credential_id"] == "c-1"

    @pytest.mark.asyncio
    async def test_delete_404_when_credential_missing(self, client: AsyncClient):
        with patch(
            "services.passkey_service.delete_credential", return_value=False
        ):
            r = await client.delete("/auth/passkey/credentials/c-1")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_happy_path(self, client: AsyncClient):
        with patch(
            "services.passkey_service.delete_credential", return_value=True
        ):
            r = await client.delete("/auth/passkey/credentials/c-1")
        assert r.status_code == 200
        assert r.json()["deleted"] is True
