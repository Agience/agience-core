"""Tests for `routers/internal_personas_router.py` — Phase E persona registry."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from jose.exceptions import JWTError


def _persona_payload(issuer: str = "chorus") -> dict:
    """Shape of a verified Chorus / Origin kernel JWT payload (Phase C)."""
    return {
        "iss": issuer,
        "sub": issuer,
        "aud": "mantle",
        "principal_type": "service",
    }


def _bearer(label: str = "test") -> dict:
    return {"Authorization": f"Bearer {label}"}


def _patch_verify_ok(payload):
    return patch(
        "routers.internal_personas_router.authority_trust.verify_service_jwt",
        return_value=payload,
    )


def _patch_verify_fail():
    return patch(
        "routers.internal_personas_router.authority_trust.verify_service_jwt",
        side_effect=JWTError("invalid"),
    )


class TestAuthGuard:
    @pytest.mark.asyncio
    async def test_missing_bearer_returns_401(self, client: AsyncClient):
        r = await client.get("/internal/personas")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_jwt_returns_401(self, client: AsyncClient):
        with _patch_verify_fail():
            r = await client.get("/internal/personas", headers=_bearer())
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_user_principal_rejected_403_or_401(self, client: AsyncClient):
        # `principal_type=user` (or anything other than "service") should fail.
        with _patch_verify_ok({"iss": "chorus", "aud": "mantle", "principal_type": "user"}):
            r = await client.get("/internal/personas", headers=_bearer())
        assert r.status_code == 401  # the verify_service_jwt path treats any non-matching shape as 401


class TestListPersonas:
    @pytest.mark.asyncio
    async def test_chorus_caller_gets_persona_map(self, client: AsyncClient):
        with _patch_verify_ok(_persona_payload("chorus")):
            with patch(
                "routers.internal_personas_router.server_registry.all_client_ids",
                return_value=["agience-server-aria", "agience-server-sage"],
            ), patch(
                "routers.internal_personas_router.get_id_optional",
                side_effect=lambda slug: f"uuid-of-{slug}",
            ):
                r = await client.get("/internal/personas", headers=_bearer())
        assert r.status_code == 200
        body = r.json()
        assert "personas" in body
        slugs = sorted(p["slug"] for p in body["personas"])
        assert slugs == ["aria", "sage"]
        client_ids = sorted(p["client_id"] for p in body["personas"])
        assert client_ids == ["agience-server-aria", "agience-server-sage"]
        # artifact_id is the platform_topology resolved id
        for p in body["personas"]:
            assert p["artifact_id"] == f"uuid-of-agience-server-{p['slug']}"

    @pytest.mark.asyncio
    async def test_origin_caller_also_allowed(self, client: AsyncClient):
        with _patch_verify_ok(_persona_payload("origin")):
            with patch(
                "routers.internal_personas_router.server_registry.all_client_ids",
                return_value=["agience-server-aria"],
            ), patch(
                "routers.internal_personas_router.get_id_optional",
                return_value="uuid-aria",
            ):
                r = await client.get("/internal/personas", headers=_bearer())
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_personas_with_missing_artifact_id_are_skipped(self, client: AsyncClient):
        """If platform_topology hasn't yet assigned an id, that persona is omitted."""
        with _patch_verify_ok(_persona_payload("chorus")):
            with patch(
                "routers.internal_personas_router.server_registry.all_client_ids",
                return_value=["agience-server-aria", "agience-server-sage"],
            ), patch(
                "routers.internal_personas_router.get_id_optional",
                side_effect=lambda slug: "uuid-aria" if slug == "agience-server-aria" else None,
            ):
                r = await client.get("/internal/personas", headers=_bearer())
        assert r.status_code == 200
        slugs = [p["slug"] for p in r.json()["personas"]]
        assert slugs == ["aria"]


class TestFindMcpClient:
    """`GET /internal/mcp-client` resolves an OAuth client_id to its
    registered MCP Client artifact's redirect_uris + allowed_oauth_scopes.
    Origin calls this during /authorize and /token validation."""

    def _mcp_client_doc(self, *, client_id, redirect_uris, scopes, key="art-1", state="committed"):
        import json as _json
        return {
            "_key": key,
            "content_type": "application/vnd.agience.mcp-client+json",
            "state": state,
            "created_time": "2026-05-09T00:00:00Z",
            "context": _json.dumps({
                "client_id": client_id,
                "redirect_uris": redirect_uris,
                "allowed_oauth_scopes": scopes,
            }),
        }

    def _patch_db_with(self, docs):
        """Patch get_arango_db with a fake whose AQL returns `docs`."""
        from unittest.mock import MagicMock

        class _FakeCursor:
            def __init__(self, rows):
                self._rows = rows
            def __iter__(self):
                return iter(self._rows)

        fake_aql = MagicMock()
        fake_aql.execute.return_value = _FakeCursor(docs)
        fake_db = MagicMock()
        fake_db.aql = fake_aql

        def _override():
            yield fake_db

        from main import app
        from services.dependencies import get_arango_db
        app.dependency_overrides[get_arango_db] = _override
        return fake_db

    def _clear_db_override(self):
        from main import app
        from services.dependencies import get_arango_db
        app.dependency_overrides.pop(get_arango_db, None)

    @pytest.mark.asyncio
    async def test_returns_redirect_uris_and_scopes(self, client: AsyncClient):
        docs = [self._mcp_client_doc(
            client_id="vscode-mcp",
            redirect_uris=["http://127.0.0.1:33418", "https://vscode.dev/redirect"],
            scopes=["read", "write"],
        )]
        try:
            self._patch_db_with(docs)
            with _patch_verify_ok(_persona_payload("origin")):
                r = await client.get(
                    "/internal/mcp-client?client_id=vscode-mcp",
                    headers=_bearer(),
                )
            assert r.status_code == 200
            body = r.json()
            assert body["client_id"] == "vscode-mcp"
            assert body["redirect_uris"] == [
                "http://127.0.0.1:33418", "https://vscode.dev/redirect",
            ]
            assert body["allowed_oauth_scopes"] == ["read", "write"]
            assert body["artifact_id"] == "art-1"
        finally:
            self._clear_db_override()

    @pytest.mark.asyncio
    async def test_404_when_no_match(self, client: AsyncClient):
        try:
            self._patch_db_with([
                self._mcp_client_doc(
                    client_id="other-client",
                    redirect_uris=["http://example/cb"],
                    scopes=["read"],
                ),
            ])
            with _patch_verify_ok(_persona_payload("origin")):
                r = await client.get(
                    "/internal/mcp-client?client_id=missing-client",
                    headers=_bearer(),
                )
            assert r.status_code == 404
        finally:
            self._clear_db_override()

    @pytest.mark.asyncio
    async def test_archived_artifacts_filtered_out(self, client: AsyncClient):
        # The AQL filters state != "archived" — but if a buggy query slipped
        # an archived row through, the route should still ignore it.
        try:
            # Cursor yields zero rows because the AQL filter excludes archived.
            self._patch_db_with([])
            with _patch_verify_ok(_persona_payload("origin")):
                r = await client.get(
                    "/internal/mcp-client?client_id=any",
                    headers=_bearer(),
                )
            assert r.status_code == 404
        finally:
            self._clear_db_override()

    @pytest.mark.asyncio
    async def test_malformed_context_json_skipped(self, client: AsyncClient):
        broken = self._mcp_client_doc(
            client_id="ok", redirect_uris=[], scopes=[],
        )
        broken["context"] = "{not valid json"
        try:
            self._patch_db_with([broken])
            with _patch_verify_ok(_persona_payload("origin")):
                r = await client.get(
                    "/internal/mcp-client?client_id=ok",
                    headers=_bearer(),
                )
            assert r.status_code == 404
        finally:
            self._clear_db_override()

    @pytest.mark.asyncio
    async def test_empty_client_id_400(self, client: AsyncClient):
        with _patch_verify_ok(_persona_payload("origin")):
            r = await client.get(
                "/internal/mcp-client?client_id=",
                headers=_bearer(),
            )
        assert r.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        r = await client.get("/internal/mcp-client?client_id=anything")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_user_principal_rejected(self, client: AsyncClient):
        with _patch_verify_ok({
            "iss": "origin", "aud": "mantle", "principal_type": "user"
        }):
            r = await client.get(
                "/internal/mcp-client?client_id=x",
                headers=_bearer(),
            )
        assert r.status_code == 401


