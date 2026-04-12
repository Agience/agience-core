"""Tests for ``server_credentials_router.py`` -- CRUD for kernel server identity.

Auth/db dependencies are overridden in ``conftest.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

NOW_ISO = datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()


@dataclass
class ServerCredentialStub:
    """Minimal stub matching ``ServerCredential`` entity shape."""

    id: str = "cred-1"
    client_id: str = "agience-server-aria"
    name: str = "Aria server"
    secret_hash: str = "$2b$12$fakehashvalue"
    authority: str = "my.agience.ai"
    host_id: str = "host-1"
    server_id: str = "server-1"
    scopes: List[str] = field(default_factory=lambda: ["resource:*:*"])
    resource_filters: Dict[str, Any] = field(default_factory=dict)
    user_id: str = "user-123"
    is_active: bool = True
    created_time: str = NOW_ISO
    modified_time: str = NOW_ISO
    last_used_at: Optional[str] = None
    last_rotated_at: Optional[str] = None


class TestServerCredentialCRUD:

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router._hash_secret", return_value="$2b$12$fakehashvalue")
    @patch("routers.server_credentials_router.db_get_by_client_id")
    @patch("routers.server_credentials_router.db_create")
    async def test_register_returns_secret(self, mock_create, mock_get, mock_hash, client):
        mock_get.return_value = None  # no conflict
        mock_create.side_effect = lambda _db, entity: entity

        payload = {
            "client_id": "agience-server-aria",
            "name": "Aria",
            "server_id": "server-1",
            "host_id": "host-1",
            "scopes": ["resource:*:*"],
            "resource_filters": {},
        }

        resp = await client.post("/server-credentials", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["client_id"] == "agience-server-aria"
        assert data["client_secret"].startswith("scs_")
        assert "secret_hash" not in data

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router.db_get_by_client_id")
    async def test_register_conflict(self, mock_get, client):
        mock_get.return_value = ServerCredentialStub()

        payload = {
            "client_id": "agience-server-aria",
            "name": "Aria",
            "server_id": "server-1",
            "host_id": "host-1",
            "scopes": ["resource:*:*"],
            "resource_filters": {},
        }

        resp = await client.post("/server-credentials", json=payload)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router.db_get_all")
    async def test_list_credentials(self, mock_get_all, client):
        mock_get_all.return_value = [
            ServerCredentialStub(id="c1", client_id="server-a"),
            ServerCredentialStub(id="c2", client_id="server-b"),
        ]

        resp = await client.get("/server-credentials")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["client_id"] == "server-a"
        # Secrets should never appear in list
        assert "client_secret" not in data[0]
        assert "secret_hash" not in data[0]

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router.db_get_by_client_id")
    async def test_get_credential(self, mock_get, client):
        mock_get.return_value = ServerCredentialStub()

        resp = await client.get("/server-credentials/agience-server-aria")
        assert resp.status_code == 200
        data = resp.json()
        assert data["client_id"] == "agience-server-aria"
        assert "client_secret" not in data
        assert "secret_hash" not in data

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router.db_get_by_client_id")
    async def test_get_credential_not_found(self, mock_get, client):
        mock_get.return_value = None

        resp = await client.get("/server-credentials/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router.db_update")
    @patch("routers.server_credentials_router.db_get_by_client_id")
    async def test_update_credential(self, mock_get, mock_update, client):
        stub = ServerCredentialStub()
        mock_get.return_value = stub
        mock_update.return_value = None

        resp = await client.patch(
            "/server-credentials/agience-server-aria",
            json={"name": "Aria v2", "is_active": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Aria v2"
        assert data["is_active"] is False

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router.db_get_by_client_id")
    async def test_update_not_found(self, mock_get, client):
        mock_get.return_value = None

        resp = await client.patch(
            "/server-credentials/nope",
            json={"name": "X"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router.db_delete")
    @patch("routers.server_credentials_router.db_get_by_client_id")
    async def test_delete_credential(self, mock_get, mock_delete, client):
        mock_get.return_value = ServerCredentialStub()
        mock_delete.return_value = None

        resp = await client.delete("/server-credentials/agience-server-aria")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router.db_get_by_client_id")
    async def test_delete_not_found(self, mock_get, client):
        mock_get.return_value = None

        resp = await client.delete("/server-credentials/nope")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router._hash_secret", return_value="$2b$12$fakehashvalue")
    @patch("routers.server_credentials_router.db_update")
    @patch("routers.server_credentials_router.db_get_by_client_id")
    async def test_rotate_returns_new_secret(self, mock_get, mock_update, mock_hash, client):
        stub = ServerCredentialStub()
        mock_get.return_value = stub
        mock_update.return_value = None

        resp = await client.post("/server-credentials/agience-server-aria/rotate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["client_id"] == "agience-server-aria"
        assert data["client_secret"].startswith("scs_")
        assert data["last_rotated_at"] is not None

    @pytest.mark.asyncio
    @patch("routers.server_credentials_router.db_get_by_client_id")
    async def test_rotate_not_found(self, mock_get, client):
        mock_get.return_value = None

        resp = await client.post("/server-credentials/nope/rotate")
        assert resp.status_code == 404
