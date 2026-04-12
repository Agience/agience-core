"""
Tests for routers/types_router.py — content-type resolution endpoints.

Covers:
  - GET /types/index  → list of available content type strings
  - GET /types/resolve?content_type=...  → full type definition or 404
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# GET /types/index
# ---------------------------------------------------------------------------

class TestListTypes:
    @pytest.mark.asyncio
    async def test_returns_list_of_content_types(self, client: AsyncClient):
        with patch(
            "services.types_service.list_available_content_types",
            return_value=[
                "application/vnd.agience.workspace+json",
                "application/vnd.agience.collection+json",
                "application/json",
            ],
        ):
            r = await client.get("/types/index")

        assert r.status_code == 200
        body = r.json()
        assert "content_types" in body
        assert "application/json" in body["content_types"]
        assert len(body["content_types"]) == 3

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_types_registered(self, client: AsyncClient):
        with patch("services.types_service.list_available_content_types", return_value=[]):
            r = await client.get("/types/index")

        assert r.status_code == 200
        assert r.json() == {"content_types": []}


# ---------------------------------------------------------------------------
# GET /types/resolve
# ---------------------------------------------------------------------------

class TestResolveType:
    @pytest.mark.asyncio
    async def test_returns_definition_for_known_content_type(self, client: AsyncClient):
        mock_result = MagicMock()
        mock_result.content_type = "application/vnd.agience.workspace+json"
        mock_result.definition = {"id": "application/vnd.agience.workspace+json", "label": "Workspace"}
        mock_result.sources = ["types/application/vnd.agience.workspace+json/type.json"]
        mock_result.validation_errors = []

        with patch("services.types_service.resolve_type_definition", return_value=mock_result):
            r = await client.get(
                "/types/resolve",
                params={"content_type": "application/vnd.agience.workspace+json"},
            )

        assert r.status_code == 200
        body = r.json()
        assert body["content_type"] == "application/vnd.agience.workspace+json"
        assert body["definition"]["label"] == "Workspace"
        assert body["sources"] == ["types/application/vnd.agience.workspace+json/type.json"]
        assert body["validation_errors"] == []

    @pytest.mark.asyncio
    async def test_404_for_unknown_content_type(self, client: AsyncClient):
        with patch("services.types_service.resolve_type_definition", return_value=None):
            r = await client.get(
                "/types/resolve",
                params={"content_type": "application/vnd.unknown.type+json"},
            )

        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_422_when_content_type_param_missing(self, client: AsyncClient):
        r = await client.get("/types/resolve")
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_validation_errors_when_type_has_schema_issues(self, client: AsyncClient):
        mock_result = MagicMock()
        mock_result.content_type = "application/vnd.agience.broken+json"
        mock_result.definition = {}
        mock_result.sources = []
        mock_result.validation_errors = ["missing required field: id", "missing required field: label"]

        with patch("services.types_service.resolve_type_definition", return_value=mock_result):
            r = await client.get(
                "/types/resolve",
                params={"content_type": "application/vnd.agience.broken+json"},
            )

        assert r.status_code == 200
        body = r.json()
        assert len(body["validation_errors"]) == 2
        assert "missing required field: id" in body["validation_errors"]
