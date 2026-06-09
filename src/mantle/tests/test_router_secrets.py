"""Tests for ``secrets_router.py`` -- generic secret CRUD endpoints."""

from dataclasses import dataclass, field
import pytest
from datetime import datetime
from unittest.mock import patch


_FIXED_ISO = datetime(2025, 1, 2, 12, 0, 0).isoformat()


@dataclass
class SecretStub:
    """Lightweight stub matching ``secrets_service.SecretConfig``."""

    id: str = "sec_1"
    type: str = "llm_key"
    provider: str = "openai"
    label: str = "My Key"
    encrypted_value: str = "gAAAA..."
    created_time: str = field(default_factory=lambda: _FIXED_ISO)
    is_default: bool = False
    authorizer_id: str = ""
    expires_at: str = ""


class TestListSecrets:
    """GET /secrets"""

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_list_secrets(self, mock_svc, client):
        mock_svc.list_secrets.return_value = [SecretStub()]

        response = await client.get("/secrets")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "sec_1"
        assert data[0]["type"] == "llm_key"
        assert data[0]["provider"] == "openai"
        assert data[0]["label"] == "My Key"
        assert data[0]["is_default"] is False
        # encrypted value never exposed (None when not requested)
        assert data[0].get("encrypted_value") is None
        assert "value" not in data[0]

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_list_secrets_empty(self, mock_svc, client):
        mock_svc.list_secrets.return_value = []
        response = await client.get("/secrets")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_list_secrets_filter_type(self, mock_svc, client):
        mock_svc.list_secrets.return_value = [SecretStub(type="github_token")]

        response = await client.get("/secrets?type=github_token")

        assert response.status_code == 200
        mock_svc.list_secrets.assert_called_once()
        call_kwargs = mock_svc.list_secrets.call_args
        assert call_kwargs[1]["secret_type"] == "github_token" or call_kwargs[0][2] == "github_token"

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_list_secrets_filter_provider(self, mock_svc, client):
        mock_svc.list_secrets.return_value = []

        response = await client.get("/secrets?provider=anthropic")

        assert response.status_code == 200
        mock_svc.list_secrets.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_list_secrets_filter_both(self, mock_svc, client):
        mock_svc.list_secrets.return_value = []

        response = await client.get("/secrets?type=llm_key&provider=openai")

        assert response.status_code == 200


class TestAddSecret:
    """POST /secrets"""

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_add_secret(self, mock_svc, client):
        stub = SecretStub(id="sec_new", is_default=True)
        mock_svc.add_secret.return_value = [stub]

        payload = {
            "type": "llm_key",
            "provider": "openai",
            "label": "My Key",
            "value": "sk-test123",
            "is_default": True,
        }
        response = await client.post("/secrets", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "sec_new"
        assert data[0]["is_default"] is True

        mock_svc.add_secret.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_add_secret_github_token(self, mock_svc, client):
        stub = SecretStub(id="sec_gh", type="github_token", provider="github", label="GH Token")
        mock_svc.add_secret.return_value = [stub]

        payload = {
            "type": "github_token",
            "provider": "github",
            "label": "GH Token",
            "value": "ghp_xxx",
        }
        response = await client.post("/secrets", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data[0]["type"] == "github_token"
        assert data[0]["provider"] == "github"

    @pytest.mark.asyncio
    async def test_add_secret_missing_fields(self, client):
        """Missing required fields -> 422."""
        response = await client.post("/secrets", json={"type": "llm_key"})
        assert response.status_code == 422


class TestDeleteSecret:
    """DELETE /secrets/{id}"""

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_delete_secret(self, mock_svc, client):
        mock_svc.delete_secret.return_value = []

        response = await client.delete("/secrets/sec_1")

        assert response.status_code == 200
        assert response.json() == []
        mock_svc.delete_secret.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_delete_secret_returns_remaining(self, mock_svc, client):
        remaining = SecretStub(id="sec_2", provider="anthropic")
        mock_svc.delete_secret.return_value = [remaining]

        response = await client.delete("/secrets/sec_1")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "sec_2"


class TestSetDefaultSecret:
    """POST /secrets/{id}/set-default"""

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_set_default(self, mock_svc, client):
        stub = SecretStub(id="sec_1", is_default=True)
        mock_svc.set_default_secret.return_value = [stub]

        response = await client.post("/secrets/sec_1/set-default")

        assert response.status_code == 200
        data = response.json()
        assert data[0]["is_default"] is True
        mock_svc.set_default_secret.assert_called_once()

    @pytest.mark.asyncio
    @patch("routers.secrets_router.secrets_service")
    async def test_set_default_clears_others(self, mock_svc, client):
        """After set-default, only the target should be default."""
        stubs = [
            SecretStub(id="sec_1", is_default=True),
            SecretStub(id="sec_2", is_default=False),
        ]
        mock_svc.set_default_secret.return_value = stubs

        response = await client.post("/secrets/sec_1/set-default")

        assert response.status_code == 200
        data = response.json()
        defaults = [d for d in data if d["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == "sec_1"
