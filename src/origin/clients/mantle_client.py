"""HTTP client for Origin → Mantle.

Origin owns identity but doesn't own the artifact store. Some auth flows need
to look up artifacts in Mantle — most notably MCP Client artifacts during the
OAuth `/authorize` validation. This client signs each call with Origin's
service identity (`origin.private.pem`); Mantle verifies via the inline JWKS
in the platform authority manifest (Phase C mutual JWT, no shared secret).

Single shared client instance — no per-call instantiation. Cached lookups
(short TTL) reduce Mantle round-trips during a token grant burst.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from kernel import service_identity

logger = logging.getLogger(__name__)


class MantleClient:
    """HTTP client for cross-service lookups against Mantle."""

    def __init__(self, base_uri: Optional[str] = None, *, cache_ttl_s: int = 60) -> None:
        self._base_uri = (base_uri or self._default_base()).rstrip("/")
        self._client = httpx.Client(timeout=3.0)
        self._mcp_client_cache: dict[str, tuple[float, dict]] = {}
        self._cache_ttl_s = cache_ttl_s

    @staticmethod
    def _default_base() -> str:
        import os

        return os.getenv("MANTLE_URI") or os.getenv("ORIGIN_URI") or "http://mantle:8081"

    def _service_token(self) -> str:
        """Sign a short-lived service JWT addressed to Mantle.

        Origin's lifespan calls `init_service_identity("origin")` at startup;
        tests provide the same via the conftest fixture. The service identity
        signs with `origin.private.pem`; Mantle verifies via the inline JWKS in
        the platform authority manifest.
        """
        return service_identity.sign_service_jwt(audience="mantle")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._service_token()}"}

    # ------------------------------------------------------------------
    # MCP Client artifact lookup (used by OAuth /authorize and /token)
    # ------------------------------------------------------------------
    def find_mcp_client(self, client_id: str) -> Optional[dict]:
        """Return `{"redirect_uris": [...], "allowed_oauth_scopes": [...]}` for
        a registered MCP Client artifact, or None when not found.

        Cached per-call for `cache_ttl_s` seconds.
        """
        now = time.monotonic()
        cached = self._mcp_client_cache.get(client_id)
        if cached and now - cached[0] < self._cache_ttl_s:
            return cached[1] or None

        try:
            resp = self._client.get(
                f"{self._base_uri}/internal/mcp-client",
                params={"client_id": client_id},
                headers=self._headers(),
            )
        except httpx.HTTPError:
            logger.warning("Mantle unreachable during MCP client lookup", exc_info=True)
            return None

        if resp.status_code == 404:
            self._mcp_client_cache[client_id] = (now, {})
            return None
        if resp.status_code >= 400:
            logger.warning(
                "Mantle /internal/mcp-client returned %d for client_id=%s", resp.status_code, client_id
            )
            return None

        try:
            payload = resp.json() or {}
        except ValueError:
            return None
        result = {
            "redirect_uris": list(payload.get("redirect_uris") or []),
            "allowed_oauth_scopes": list(payload.get("allowed_oauth_scopes") or []),
        }
        self._mcp_client_cache[client_id] = (now, result)
        return result


# Module-level singleton — built lazily so tests can override env vars before construction.
_mantle_client: Optional[MantleClient] = None


def get_mantle_client() -> MantleClient:
    global _mantle_client
    if _mantle_client is None:
        _mantle_client = MantleClient()
    return _mantle_client


def reset_mantle_client() -> None:
    """Test hook — drop the singleton so the next call rebuilds with current env."""
    global _mantle_client
    _mantle_client = None
