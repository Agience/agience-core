"""Tests for routers/setup_router.py — first-boot wizard.

Covers the routes that gate platform initialization:
  - GET /setup/status — version + needs_setup flag from platform_settings
  - POST /setup/validate-token — token comparison without consumption
  - POST /setup/validate-connection — service-by-service connectivity probes
  - POST /setup/complete — operator creation, settings persistence, JWT issuance,
    re-running rejected when setup is already complete

The setup token gate is the first-boot security boundary; the X-Setup-Token
header tests below lock down the 403 / 410 / 200 paths.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# /setup/status
# ---------------------------------------------------------------------------

class TestSetupStatus:
    @pytest.mark.asyncio
    async def test_status_reports_needs_setup_flag(self, client: AsyncClient):
        with patch(
            "routers.setup_router.platform_settings.needs_setup", return_value=True
        ):
            resp = await client.get("/setup/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["needs_setup"] is True
        assert "version" in body
        assert "env_defaults" in body

    @pytest.mark.asyncio
    async def test_status_includes_openai_env_default(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with patch(
            "routers.setup_router.platform_settings.needs_setup", return_value=False
        ):
            resp = await client.get("/setup/status")
        assert resp.json()["env_defaults"]["openai_api_key"] is True


# ---------------------------------------------------------------------------
# /setup/validate-token
# ---------------------------------------------------------------------------

class TestValidateToken:
    @pytest.mark.asyncio
    async def test_returns_valid_true_when_token_matches(self, client: AsyncClient):
        with patch("core.key_manager.get_setup_token", return_value="abc123"):
            resp = await client.post("/setup/validate-token", json={"token": "abc123"})
        assert resp.status_code == 200
        assert resp.json() == {"valid": True}

    @pytest.mark.asyncio
    async def test_returns_valid_false_when_token_mismatches(self, client: AsyncClient):
        with patch("core.key_manager.get_setup_token", return_value="abc123"):
            resp = await client.post("/setup/validate-token", json={"token": "WRONG"})
        assert resp.status_code == 200
        assert resp.json() == {"valid": False}

    @pytest.mark.asyncio
    async def test_410_when_setup_already_completed(self, client: AsyncClient):
        with patch("core.key_manager.get_setup_token", return_value=None):
            resp = await client.post("/setup/validate-token", json={"token": "abc"})
        assert resp.status_code == 410
        assert "completed" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /setup/validate-connection
# ---------------------------------------------------------------------------

class TestValidateConnection:
    @pytest.mark.asyncio
    async def test_403_without_setup_token(self, client: AsyncClient):
        with patch("core.key_manager.get_setup_token", return_value="real-token"):
            resp = await client.post(
                "/setup/validate-connection",
                json={"service": "openai", "config": {"api_key": "x"}},
                headers={"X-Setup-Token": "WRONG"},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_410_when_setup_already_done(self, client: AsyncClient):
        with patch("core.key_manager.get_setup_token", return_value=None):
            resp = await client.post(
                "/setup/validate-connection",
                json={"service": "openai", "config": {}},
                headers={"X-Setup-Token": "anything"},
            )
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_unknown_service_returns_error_payload_not_5xx(self, client: AsyncClient):
        with patch("core.key_manager.get_setup_token", return_value="t"):
            resp = await client.post(
                "/setup/validate-connection",
                json={"service": "mystery", "config": {}},
                headers={"X-Setup-Token": "t"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"success": False, "error": "Unknown service: mystery"}

    @pytest.mark.asyncio
    async def test_arango_failure_is_caught(self, client: AsyncClient):
        with (
            patch("core.key_manager.get_setup_token", return_value="t"),
            patch(
                "schemas.arango.initialize.get_arangodb_connection",
                side_effect=RuntimeError("connection refused"),
            ),
        ):
            resp = await client.post(
                "/setup/validate-connection",
                json={"service": "arango", "config": {"host": "x"}},
                headers={"X-Setup-Token": "t"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "connection refused" in body["error"]


# ---------------------------------------------------------------------------
# /setup/complete
# ---------------------------------------------------------------------------

class TestSetupComplete:
    @pytest.mark.asyncio
    async def test_403_with_wrong_setup_token(self, client: AsyncClient):
        with patch("core.key_manager.get_setup_token", return_value="real-token"):
            resp = await client.post(
                "/setup/complete",
                json={"settings": []},
                headers={"X-Setup-Token": "WRONG"},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_410_when_setup_already_completed(self, client: AsyncClient):
        with (
            patch("core.key_manager.get_setup_token", return_value="t"),
            patch(
                "routers.setup_router.platform_settings.needs_setup", return_value=False
            ),
        ):
            resp = await client.post(
                "/setup/complete",
                json={"settings": []},
                headers={"X-Setup-Token": "t"},
            )
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_short_password_rejected_422(self, client: AsyncClient):
        with (
            patch("core.key_manager.get_setup_token", return_value="t"),
            patch("routers.setup_router.platform_settings.needs_setup", return_value=True),
        ):
            resp = await client.post(
                "/setup/complete",
                headers={"X-Setup-Token": "t"},
                json={
                    "operator": {
                        "email": "op@example.com",
                        "password": "short",  # < 12 chars
                        "name": "Op",
                    },
                    "settings": [],
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_completes_with_operator_and_returns_jwts(self, client: AsyncClient):
        """Happy path: operator account created, settings persisted, JWTs returned."""
        captured_settings: list[list[dict]] = []

        def fake_set_many(db, dicts, **kwargs):
            captured_settings.append(list(dicts))

        with (
            patch("core.key_manager.get_setup_token", return_value="t"),
            patch("routers.setup_router.platform_settings.needs_setup", return_value=True),
            patch(
                "routers.setup_router.platform_settings.set_many", side_effect=fake_set_many
            ),
            patch("routers.setup_router.platform_settings.delete_keys"),
            patch("routers.setup_router.arango_ws.create_person"),
            patch("search.init_search.ensure_search_indices_exist"),
            patch("services.workspace_service.create_workspace"),
            patch("core.config.load_settings_from_db"),
            patch("core.key_manager.delete_setup_token"),
            patch("main.run_phase4_after_setup"),
        ):
            resp = await client.post(
                "/setup/complete",
                headers={"X-Setup-Token": "t"},
                json={
                    "operator": {
                        "email": "op@example.com",
                        "password": "long-enough-pw",
                        "name": "Op",
                    },
                    "settings": [
                        {
                            "key": "ai.openai.api_key",
                            "value": "sk-test",
                            "category": "ai",
                            "is_secret": True,
                        }
                    ],
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "bearer"

        # The settings batch always includes platform.setup_complete=true and
        # the operator_id pin so subsequent reboots do not enter setup mode.
        flat_keys = {s["key"] for batch in captured_settings for s in batch}
        assert "platform.setup_complete" in flat_keys
        assert "platform.operator_id" in flat_keys
        assert "ai.openai.api_key" in flat_keys

    @pytest.mark.asyncio
    async def test_completes_without_operator_pins_setup_token_for_promotion(
        self, client: AsyncClient
    ):
        """Operator-less setup (Google-only flow) stores the setup token in
        platform_settings for first-login promotion."""
        captured_keys: set[str] = set()

        def fake_set_many(db, dicts, **kwargs):
            for d in dicts:
                captured_keys.add(d["key"])

        with (
            patch("core.key_manager.get_setup_token", return_value="raw-setup-token"),
            patch("routers.setup_router.platform_settings.needs_setup", return_value=True),
            patch(
                "routers.setup_router.platform_settings.set_many", side_effect=fake_set_many
            ),
            patch("routers.setup_router.platform_settings.delete_keys"),
            patch("core.config.load_settings_from_db"),
            patch("core.key_manager.delete_setup_token"),
            patch("main.run_phase4_after_setup"),
        ):
            resp = await client.post(
                "/setup/complete",
                headers={"X-Setup-Token": "raw-setup-token"},
                json={"settings": []},
            )

        assert resp.status_code == 200
        # No JWTs when no operator was created.
        assert resp.json()["access_token"] == ""
        # Setup token is captured for the operator-promotion path.
        assert "platform.setup_operator_token" in captured_keys
        assert "platform.setup_complete" in captured_keys
        # operator_id was NOT set since no account was created.
        assert "platform.operator_id" not in captured_keys
