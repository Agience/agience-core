"""HTTP client for Mantle → Origin.

Mantle needs Origin for cross-service identity lookups: API key verification,
grant checks, delegation-token issuance for proxied user requests. Phase C:
Mantle signs each call with its own service identity (`mantle.private.pem`);
Origin verifies via the inline JWKS in the platform authority manifest. No
shared secret, no /auth/token round-trip.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from kernel import service_identity
from entities.api_key import APIKey as APIKeyEntity
from entities.grant import Grant as GrantEntity

logger = logging.getLogger(__name__)


class OriginClient:
    """HTTP shim to Origin for cross-service identity lookups."""

    def __init__(self, base_uri: Optional[str] = None) -> None:
        import os

        self._base = (base_uri or os.getenv("ORIGIN_URI") or "http://origin:8080").rstrip("/")
        self._client = httpx.Client(timeout=3.0)

    def _service_token(self) -> str:
        """Sign a short-lived service JWT addressed to Origin.

        Mantle's lifespan must have called `service_identity.init_service_identity("mantle")`
        at startup. Tests provide the same setup via the conftest fixture.
        """
        return service_identity.sign_service_jwt(audience="origin")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._service_token()}",
            "Content-Type": "application/json",
        }

    def verify_api_key(self, token: str) -> Optional[tuple[APIKeyEntity, list[GrantEntity]]]:
        """Call Origin `POST /auth/keys/verify`. Returns (entity, grants) or None."""
        try:
            resp = self._client.post(
                f"{self._base}/auth/keys/verify",
                json={"token": token},
                headers=self._headers(),
            )
        except httpx.HTTPError:
            logger.warning("Origin unreachable during verify_api_key", exc_info=True)
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.warning("Origin /auth/keys/verify returned %d", resp.status_code)
            return None
        try:
            payload = resp.json()
        except ValueError:
            return None

        api_key_data = payload.get("api_key") or {}
        api_key = APIKeyEntity.from_dict(api_key_data)
        grants = [GrantEntity.from_dict(g) for g in payload.get("grants") or []]
        return api_key, grants

    # ------------------------------------------------------------------
    # Grants — direct lookups against Origin (replaces Arango-backed reads).
    # ------------------------------------------------------------------
    def check_grant(
        self, *, principal_id: str, resource_id: str, action: str
    ) -> Optional[dict]:
        """Direct grant check. Returns the JSON dict or None on transport error."""
        try:
            resp = self._client.get(
                f"{self._base}/auth/grants/check",
                params={"principal": principal_id, "resource": resource_id, "action": action},
                headers=self._headers(),
            )
        except httpx.HTTPError:
            logger.warning("Origin unreachable during check_grant", exc_info=True)
            return None
        if resp.status_code != 200:
            logger.warning("Origin /auth/grants/check returned %d", resp.status_code)
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def lookup_grants_by_key(self, token: str) -> list[GrantEntity]:
        try:
            resp = self._client.post(
                f"{self._base}/auth/grants/lookup-by-key",
                json={"token": token},
                headers=self._headers(),
            )
        except httpx.HTTPError:
            logger.warning("Origin unreachable during lookup_grants_by_key", exc_info=True)
            return []
        if resp.status_code != 200:
            return []
        try:
            payload = resp.json()
        except ValueError:
            return []
        return [GrantEntity.from_dict(g) for g in (payload.get("grants") or [])]

    def list_grants_by_principal_resource(
        self, *, grantee_id: str, resource_id: str
    ) -> list[GrantEntity]:
        try:
            resp = self._client.get(
                f"{self._base}/auth/grants/by-principal-resource",
                params={"grantee_id": grantee_id, "resource_id": resource_id},
                headers=self._headers(),
            )
        except httpx.HTTPError:
            return []
        if resp.status_code != 200:
            return []
        try:
            payload = resp.json()
        except ValueError:
            return []
        return [GrantEntity.from_dict(g) for g in (payload.get("grants") or [])]

    def list_grants_by_grantee(
        self, grantee_id: str, grantee_type: str = "user"
    ) -> list[GrantEntity]:
        try:
            resp = self._client.get(
                f"{self._base}/auth/grants/by-grantee",
                params={"grantee_id": grantee_id, "grantee_type": grantee_type},
                headers=self._headers(),
            )
        except httpx.HTTPError:
            return []
        if resp.status_code != 200:
            return []
        try:
            payload = resp.json()
        except ValueError:
            return []
        return [GrantEntity.from_dict(g) for g in (payload.get("grants") or [])]

    def upsert_user_grant(
        self,
        *,
        user_id: str,
        resource_id: str,
        granted_by: str,
        flags: dict,
        name: Optional[str] = None,
    ) -> tuple[Optional[GrantEntity], bool]:
        body = {
            "user_id": user_id,
            "resource_id": resource_id,
            "granted_by": granted_by,
            "flags": flags,
        }
        if name is not None:
            body["name"] = name
        try:
            resp = self._client.post(
                f"{self._base}/auth/grants/upsert",
                json=body,
                headers=self._headers(),
            )
        except httpx.HTTPError:
            return None, False
        if resp.status_code != 200:
            return None, False
        try:
            payload = resp.json()
        except ValueError:
            return None, False
        grant = GrantEntity.from_dict(payload.get("grant") or {})
        return grant, bool(payload.get("changed"))

    def issue_delegation_token(
        self, server_client_id: str, user_id: str, ttl_seconds: int = 300
    ) -> Optional[str]:
        """Mint a short-lived RFC 8693 delegation JWT via Origin.

        Used by `mcp_service` when proxying user requests to a first-party
        MCP persona. Origin owns RSA signing keys, so Mantle can't issue
        delegation JWTs directly — it calls Origin's `POST /internal/delegation-token`.

        Returns the encoded JWT string, or None when Origin is unreachable
        or rejects the request.
        """
        try:
            resp = self._client.post(
                f"{self._base}/internal/delegation-token",
                json={
                    "server_client_id": server_client_id,
                    "user_id": user_id,
                    "ttl_seconds": ttl_seconds,
                },
                headers=self._headers(),
            )
        except httpx.HTTPError:
            logger.warning(
                "Origin unreachable during issue_delegation_token", exc_info=True
            )
            return None
        if resp.status_code != 200:
            logger.warning(
                "Origin /internal/delegation-token returned %d", resp.status_code
            )
            return None
        try:
            return resp.json().get("token")
        except ValueError:
            return None

    def get_operator_id(self) -> Optional[str]:
        """Fetch the platform operator UUID from Origin.

        Used by Mantle when ``platform.operator_id`` is absent from its own
        ArangoDB platform_settings (e.g. after a factory reset that wiped
        ArangoDB but left Origin's SQLite intact).  Returns None when Origin
        is unreachable or setup has not yet completed.
        """
        try:
            resp = self._client.get(
                f"{self._base}/internal/operator-id",
                headers=self._headers(),
            )
        except httpx.HTTPError:
            logger.warning("Origin unreachable during get_operator_id", exc_info=True)
            return None
        if resp.status_code != 200:
            logger.warning("Origin /internal/operator-id returned %d", resp.status_code)
            return None
        try:
            return resp.json().get("operator_id") or None
        except ValueError:
            return None


# Module-level singleton
_origin_client: Optional[OriginClient] = None


def get_origin_client() -> OriginClient:
    global _origin_client
    if _origin_client is None:
        _origin_client = OriginClient()
    return _origin_client


def reset_origin_client() -> None:
    """Test hook."""
    global _origin_client
    _origin_client = None


# Keep `time` as an active import — referenced in inline cache logic added later
# without producing an unused-import warning today.
_ = time
