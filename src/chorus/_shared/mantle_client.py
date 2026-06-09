"""Chorus → Mantle client for artifact lookup + grant check.

The universal MCP gateway in Chorus needs to:
  1. Resolve `POST /{server_id}/mcp` requests to a `vnd.agience.mcp-server+json`
     artifact in Mantle. This client GETs the artifact.
  2. Verify the inbound caller has `can_invoke` on that artifact. The grant
     check happens in Origin (sole grant-store).

Phase C trust model: every outbound call signs a chorus service JWT via
`core.service_identity.sign_service_jwt(audience=...)`. Origin/Mantle verify
against the inline JWKS in the platform authority manifest.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

from kernel import service_identity

log = logging.getLogger(__name__)

# Chorus runs in-process with a single shared httpx.Client per peer.

# Per-server artifact cache (server_id → (expires_at_monotonic, artifact_dict)).
# Refreshed on miss or staleness; invalidated when an artifact-update event is
# seen (Phase E will wire that up; until then, the TTL is the safety net).
_ARTIFACT_CACHE_TTL_S = 60

# Timeout for service-to-service calls.  Docker→host.docker.internal on Windows
# can have noticeable latency on first connection; 10 s is tight enough to fail
# fast but generous enough not to time out during cold-start path resolution.
_TIMEOUT_S = 10.0

# Per-(server_id, principal_id) grant cache. Same TTL as Mantle's grant-check
# cache so revocation propagates within the same window.
_GRANT_CACHE_TTL_S = 60


class MantleGatewayClient:
    """HTTP client for Chorus's universal MCP gateway."""

    def __init__(self, *, mantle_uri: Optional[str] = None, origin_uri: Optional[str] = None) -> None:
        self._mantle_base = (mantle_uri or os.getenv("MANTLE_URI") or "http://localhost:8081").rstrip("/")
        self._origin_base = (origin_uri or os.getenv("ORIGIN_URI") or "http://localhost:8080").rstrip("/")
        self._http = httpx.Client(timeout=_TIMEOUT_S)
        self._artifact_cache: dict[str, tuple[float, Optional[dict]]] = {}
        self._grant_cache: dict[tuple[str, str, str], tuple[float, bool]] = {}

    # ------------------------------------------------------------------
    # Service token
    # ------------------------------------------------------------------

    def _sign(self, *, audience: str) -> str:
        """Sign a chorus service JWT. Chorus host's startup must have already
        called `init_service_identity("chorus")`."""
        return service_identity.sign_service_jwt(audience=audience)

    def _mantle_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._sign(audience='mantle')}",
            "Content-Type": "application/json",
        }

    def _origin_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._sign(audience='origin')}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Artifact lookup
    # ------------------------------------------------------------------

    def get_artifact(self, server_id: str) -> Optional[dict]:
        """Return the `vnd.agience.mcp-server+json` artifact, or None on miss/error.

        Used for `external` and `relay` kinds where dispatch needs the artifact's
        full context (e.g. `upstream_uri`). For `persona` kind, the slug→UUID
        map populated at startup via `list_personas()` is the fast path.
        """
        now = time.monotonic()
        cached = self._artifact_cache.get(server_id)
        if cached and now < cached[0]:
            return cached[1]

        try:
            resp = self._http.get(
                f"{self._mantle_base}/artifacts/{server_id}",
                headers=self._mantle_headers(),
            )
        except httpx.HTTPError:
            log.warning("Mantle unreachable during artifact lookup for %s", server_id, exc_info=True)
            return None

        if resp.status_code == 404:
            self._artifact_cache[server_id] = (now + _ARTIFACT_CACHE_TTL_S, None)
            return None
        if resp.status_code != 200:
            log.warning("Mantle /artifacts/%s returned %d", server_id, resp.status_code)
            return None

        try:
            artifact = resp.json()
        except ValueError:
            return None
        self._artifact_cache[server_id] = (now + _ARTIFACT_CACHE_TTL_S, artifact)
        return artifact

    def invalidate_artifact(self, server_id: str) -> None:
        """Drop the cached artifact entry. Call when receiving artifact.updated events."""
        self._artifact_cache.pop(server_id, None)

    # ------------------------------------------------------------------
    # Persona slug ↔ UUID map
    # ------------------------------------------------------------------

    def list_personas(self) -> list[dict]:
        """GET Mantle's `/internal/personas` and return the slug→UUID list.

        Returns `[{"slug": str, "client_id": str, "artifact_id": str}, ...]`
        on success; `[]` on transport or auth failure. Caller is responsible
        for retry / error handling.
        """
        try:
            resp = self._http.get(
                f"{self._mantle_base}/internal/personas",
                headers=self._mantle_headers(),
            )
        except httpx.HTTPError:
            log.warning("Mantle unreachable during list_personas", exc_info=True)
            return []
        if resp.status_code != 200:
            log.warning("Mantle /internal/personas returned %d", resp.status_code)
            return []
        try:
            payload = resp.json()
        except ValueError:
            return []
        return list(payload.get("personas") or [])

    # ------------------------------------------------------------------
    # Grant check (Origin)
    # ------------------------------------------------------------------

    def can_invoke(self, *, principal_id: str, server_id: str) -> bool:
        """Return True if `principal_id` has `can_invoke` on `server_id`'s artifact."""
        return self._check_grant(principal_id=principal_id, resource_id=server_id, action="invoke")

    def _check_grant(self, *, principal_id: str, resource_id: str, action: str) -> bool:
        key = (principal_id, resource_id, action)
        now = time.monotonic()
        cached = self._grant_cache.get(key)
        if cached and now < cached[0]:
            return cached[1]

        try:
            resp = self._http.get(
                f"{self._origin_base}/auth/grants/check",
                params={"principal": principal_id, "resource": resource_id, "action": action},
                headers=self._origin_headers(),
            )
        except httpx.HTTPError:
            log.warning(
                "Origin unreachable during grant check (principal=%s resource=%s)",
                principal_id, resource_id, exc_info=True,
            )
            return False

        if resp.status_code != 200:
            log.debug(
                "Origin /auth/grants/check returned %d (principal=%s resource=%s)",
                resp.status_code, principal_id, resource_id,
            )
            self._grant_cache[key] = (now + _GRANT_CACHE_TTL_S, False)
            return False

        try:
            payload = resp.json()
        except ValueError:
            return False

        allowed = bool(payload.get("allowed"))
        self._grant_cache[key] = (now + _GRANT_CACHE_TTL_S, allowed)
        return allowed


# Module-level singleton (test hook below)
_singleton: Optional[MantleGatewayClient] = None


def get_gateway_client() -> MantleGatewayClient:
    global _singleton
    if _singleton is None:
        _singleton = MantleGatewayClient()
    return _singleton


def reset_gateway_client_for_tests() -> None:
    global _singleton
    _singleton = None


def is_uuid_like(s: str) -> bool:
    """Cheap check for a UUID-shaped path segment. Avoids hitting Mantle for
    obvious non-UUIDs like `aria`, `health`, `.well-known`."""
    if len(s) != 36:
        return False
    if s[8] != "-" or s[13] != "-" or s[18] != "-" or s[23] != "-":
        return False
    return all(c in "0123456789abcdef-" for c in s.lower())
