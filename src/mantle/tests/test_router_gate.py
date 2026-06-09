"""Tests for routers/gate_router.py — internal kernel-server-only gate.

Covers:
  - Auth guard rejects missing / non-service / non-kernel tokens
  - POST /internal/gate/set-limits delegates to gate_service
  - GET /internal/gate/usage/{person_id} returns limits + usage shape

Phase C trust model: callers sign their own kernel JWTs via
`chorus.private.pem`; gate_router verifies via `core.authority_trust`. These
tests patch `routers.gate_router.authority_trust.verify_service_jwt` to return
synthetic payloads instead of minting real signed tokens.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from jose.exceptions import JWTError

from services.server_registry import all_client_ids as _all_client_ids

_KERNEL_SERVER_IDS = _all_client_ids()


def _kernel_persona_payload(client_id: str | None = None) -> dict:
    """Shape of a verified Chorus kernel JWT payload (Phase C)."""
    cid = client_id or sorted(_KERNEL_SERVER_IDS)[0]
    return {
        "iss": "chorus",
        "sub": cid,
        "aud": "mantle",
        "principal_type": "service",
        "client_id": cid,
    }


def _bearer(label: str = "test") -> dict:
    # Token value doesn't matter — verify_service_jwt is patched per test.
    return {"Authorization": f"Bearer {label}"}


def _patch_verify_ok(payload):
    """Make verify_service_jwt return `payload` (success path)."""
    return patch(
        "routers.gate_router.authority_trust.verify_service_jwt",
        return_value=payload,
    )


def _patch_verify_invalid():
    """Make verify_service_jwt raise — simulates an invalid signature/claim."""
    return patch(
        "routers.gate_router.authority_trust.verify_service_jwt",
        side_effect=JWTError("invalid"),
    )


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    @pytest.mark.asyncio
    async def test_missing_bearer_returns_401(self, client: AsyncClient):
        r = await client.get("/internal/gate/usage/user-1")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_garbage_token_returns_401(self, client: AsyncClient):
        with _patch_verify_invalid():
            r = await client.get(
                "/internal/gate/usage/user-1", headers=_bearer("not.a.token")
            )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_user_token_rejected_with_403(self, client: AsyncClient):
        # A user JWT (different principal_type) — the verify path lets it
        # through signature-wise but the guard rejects on principal_type.
        user_payload = {
            "iss": "chorus",
            "sub": "user-1",
            "aud": "mantle",
            "principal_type": "user",
        }
        with _patch_verify_ok(user_payload):
            r = await client.get(
                "/internal/gate/usage/user-1", headers=_bearer()
            )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_non_kernel_persona_token_rejected(self, client: AsyncClient):
        third_party = {
            "iss": "chorus",
            "sub": "third-party",
            "aud": "mantle",
            "principal_type": "service",
            "client_id": "third-party",
        }
        with _patch_verify_ok(third_party):
            r = await client.get(
                "/internal/gate/usage/user-1", headers=_bearer()
            )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# /internal/gate/usage
# ---------------------------------------------------------------------------

class TestGetUsage:
    @pytest.mark.asyncio
    async def test_returns_limits_and_usage_shape(self, client: AsyncClient):
        with (
            _patch_verify_ok(_kernel_persona_payload()),
            patch(
                "services.gate_service.get_or_default_limits",
                return_value={"max_workspaces": 10, "max_artifacts": 100, "vu_limit": 1000},
            ),
            patch("services.gate_service.count_workspaces", return_value=3),
            patch("services.gate_service.count_artifacts", return_value=42),
            patch("services.gate_service.get_tally", return_value=125),
        ):
            r = await client.get(
                "/internal/gate/usage/user-1", headers=_bearer()
            )
        assert r.status_code == 200
        body = r.json()
        assert body["person_id"] == "user-1"
        assert body["limits"]["vu_limit"] == 1000
        assert body["usage"] == {"workspaces": 3, "artifacts": 42, "vu": 125}


# ---------------------------------------------------------------------------
# /internal/gate/set-limits
# ---------------------------------------------------------------------------

class TestSetLimits:
    @pytest.mark.asyncio
    async def test_delegates_to_gate_service(self, client: AsyncClient):
        with (
            _patch_verify_ok(_kernel_persona_payload()),
            patch("services.gate_service.set_limits") as set_limits,
        ):
            r = await client.post(
                "/internal/gate/set-limits",
                json={
                    "person_id": "user-1",
                    "max_workspaces": 5,
                    "max_artifacts": 50,
                    "vu_limit": 500,
                },
                headers=_bearer(),
            )
        assert r.status_code == 204
        set_limits.assert_called_once()
        call_kwargs = set_limits.call_args.kwargs
        assert call_kwargs["max_workspaces"] == 5
        assert call_kwargs["vu_limit"] == 500

    @pytest.mark.asyncio
    async def test_partial_limits_supported(self, client: AsyncClient):
        with (
            _patch_verify_ok(_kernel_persona_payload()),
            patch("services.gate_service.set_limits") as set_limits,
        ):
            r = await client.post(
                "/internal/gate/set-limits",
                json={"person_id": "user-1", "vu_limit": 200},
                headers=_bearer(),
            )
        assert r.status_code == 204
        kwargs = set_limits.call_args.kwargs
        assert kwargs["vu_limit"] == 200
        assert kwargs["max_workspaces"] is None


