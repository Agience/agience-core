"""Tests for routers/otp_router.py — email OTP authentication.

Covers /auth/otp/request and /auth/otp/verify:
  - 503 when email service not configured
  - request for unknown email returns 200 (no enumeration)
  - request for known email delegates to otp_service.request_otp
  - rate-limited request → 429
  - verify wrong code → 401
  - verify orphan person → 401
  - verify happy path → JWT tokens
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


class TestRequestOtp:
    @pytest.mark.asyncio
    async def test_503_when_email_unconfigured(self, client: AsyncClient):
        with patch("services.email_service.is_configured", return_value=False):
            r = await client.post("/auth/otp/request", json={"email": "u@e.com"})
        assert r.status_code == 503

    @pytest.mark.asyncio
    async def test_unknown_email_returns_200_no_enumeration(self, client: AsyncClient):
        with (
            patch("services.email_service.is_configured", return_value=True),
            patch("db.arango_identity.get_person_by_email", return_value=None),
            patch(
                "services.otp_service.request_otp", new=AsyncMock(return_value=True)
            ) as svc,
        ):
            r = await client.post("/auth/otp/request", json={"email": "ghost@e.com"})
        assert r.status_code == 200
        assert r.json()["sent"] is True
        # Service is NOT invoked for unknown emails — that's how non-enumeration works.
        svc.assert_not_called()

    @pytest.mark.asyncio
    async def test_known_email_dispatches_otp(self, client: AsyncClient):
        with (
            patch("services.email_service.is_configured", return_value=True),
            patch(
                "db.arango_identity.get_person_by_email",
                return_value={"id": "user-1", "email": "u@e.com"},
            ),
            patch(
                "services.otp_service.request_otp", new=AsyncMock(return_value=True)
            ) as svc,
        ):
            r = await client.post("/auth/otp/request", json={"email": "u@e.com"})
        assert r.status_code == 200
        svc.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limited_returns_429(self, client: AsyncClient):
        with (
            patch("services.email_service.is_configured", return_value=True),
            patch(
                "db.arango_identity.get_person_by_email",
                return_value={"id": "user-1"},
            ),
            patch(
                "services.otp_service.request_otp", new=AsyncMock(return_value=False)
            ),
        ):
            r = await client.post("/auth/otp/request", json={"email": "u@e.com"})
        assert r.status_code == 429


class TestVerifyOtp:
    @pytest.mark.asyncio
    async def test_invalid_code_returns_401(self, client: AsyncClient):
        with patch("services.otp_service.verify_otp", return_value=None):
            r = await client.post(
                "/auth/otp/verify", json={"email": "u@e.com", "code": "000000"}
            )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_orphan_person_returns_401(self, client: AsyncClient):
        with (
            patch("services.otp_service.verify_otp", return_value="user-1"),
            patch("db.arango_identity.get_person_by_id", return_value=None),
        ):
            r = await client.post(
                "/auth/otp/verify", json={"email": "u@e.com", "code": "123456"}
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
            patch("services.otp_service.verify_otp", return_value="user-1"),
            patch("db.arango_identity.get_person_by_id", return_value=person),
        ):
            r = await client.post(
                "/auth/otp/verify", json={"email": "u@e.com", "code": "123456"}
            )
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
