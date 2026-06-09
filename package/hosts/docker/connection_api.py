"""Connection API for an Agience docker-host.

A docker-host is a containerized service that authenticates to Agience as a
trusted internal peer using the mutual-JWT trust model. This module wraps the
two things every host needs:

    1. Signing outbound calls with the host's own service identity.
    2. Verifying inbound JWTs against the platform's authority manifest.

It also bundles the most common outbound calls (artifact lookup, grant check)
so that simple hosts don't need to reach into the kernel directly.

Trust prerequisites — present at container start:

    KEYS_DIR/<service_name>.private.pem    # this host's RSA keypair
    KEYS_DIR/authority.manifest.json       # platform trust anchors (inline JWKS)

Typical use:

    from connection_api import AgienceConnection

    conn = AgienceConnection(service_name="my-host")
    conn.boot()
    artifact = conn.get_artifact(server_id)
    if conn.can_invoke(principal_id=user_id, server_id=server_id):
        ...

For inbound verification (e.g. ASGI middleware on the host's own endpoints),
use `conn.verify_service_caller(token, from_issuer="mantle")` to verify a peer
service JWT, or `conn.verify_delegation_caller(token, from_issuer="chorus")`
for an RFC-8693 delegation token. Both return the decoded claims on success
and raise on signature, audience, or expiry mismatch.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import httpx

from kernel import authority_trust, service_identity

log = logging.getLogger(__name__)

_TIMEOUT_S = 3.0
_ARTIFACT_CACHE_TTL_S = 60
_GRANT_CACHE_TTL_S = 60


class AgienceConnection:
    """Mutual-JWT connection to the Agience platform from inside a container."""

    def __init__(
        self,
        *,
        service_name: Optional[str] = None,
        mantle_uri: Optional[str] = None,
        origin_uri: Optional[str] = None,
    ) -> None:
        self._service_name = service_name or os.getenv("AGIENCE_SERVICE_NAME") or "docker-host"
        self._mantle_base = (mantle_uri or os.getenv("AGIENCE_API_URI") or "http://mantle:8081").rstrip("/")
        self._origin_base = (origin_uri or os.getenv("ORIGIN_URI") or "http://origin:8080").rstrip("/")
        self._http = httpx.Client(timeout=_TIMEOUT_S)
        self._artifact_cache: dict[str, tuple[float, Optional[dict]]] = {}
        self._grant_cache: dict[tuple[str, str, str], tuple[float, bool]] = {}
        self._booted = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def boot(self) -> None:
        """Load this host's signing key and the platform authority manifest.

        Raises if either is missing — fail fast at startup, never lazy-init.
        """
        service_identity.init_service_identity(self._service_name)
        authority_trust.load_authority_manifest()
        self._booted = True
        log.info("AgienceConnection booted as service=%s", self._service_name)

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------
    # Outbound: signing
    # ------------------------------------------------------------------

    def sign(self, *, audience: str) -> str:
        """Sign a service JWT for the named peer (e.g. 'mantle', 'origin')."""
        if not self._booted:
            raise RuntimeError("AgienceConnection not booted — call .boot() first")
        return service_identity.sign_service_jwt(audience=audience)

    def _mantle_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.sign(audience='mantle')}",
            "Content-Type": "application/json",
        }

    def _origin_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.sign(audience='origin')}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Outbound: artifacts (Mantle)
    # ------------------------------------------------------------------

    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        """Return the artifact document, or None on miss/error."""
        now = time.monotonic()
        cached = self._artifact_cache.get(artifact_id)
        if cached and now < cached[0]:
            return cached[1]

        try:
            resp = self._http.get(
                f"{self._mantle_base}/artifacts/{artifact_id}",
                headers=self._mantle_headers(),
            )
        except httpx.HTTPError:
            log.warning("Mantle unreachable during artifact lookup for %s", artifact_id, exc_info=True)
            return None

        if resp.status_code == 404:
            self._artifact_cache[artifact_id] = (now + _ARTIFACT_CACHE_TTL_S, None)
            return None
        if resp.status_code != 200:
            log.warning("Mantle /artifacts/%s returned %d", artifact_id, resp.status_code)
            return None

        try:
            artifact = resp.json()
        except ValueError:
            return None
        self._artifact_cache[artifact_id] = (now + _ARTIFACT_CACHE_TTL_S, artifact)
        return artifact

    def invalidate_artifact(self, artifact_id: str) -> None:
        self._artifact_cache.pop(artifact_id, None)

    # ------------------------------------------------------------------
    # Outbound: grants (Origin)
    # ------------------------------------------------------------------

    def can_invoke(self, *, principal_id: str, server_id: str) -> bool:
        return self._check_grant(principal_id=principal_id, resource_id=server_id, action="invoke")

    def can_read(self, *, principal_id: str, resource_id: str) -> bool:
        return self._check_grant(principal_id=principal_id, resource_id=resource_id, action="read")

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

    # ------------------------------------------------------------------
    # Inbound: verification
    # ------------------------------------------------------------------

    def verify_service_caller(
        self,
        token: str,
        *,
        from_issuer: str,
        expected_audience: Optional[str] = None,
    ) -> dict[str, Any]:
        """Verify an inbound peer-service JWT.

        `from_issuer` is the named service that signed the token (e.g. "mantle",
        "origin", "chorus"). Its public key must be listed in the authority
        manifest. `expected_audience` defaults to this host's service name.
        Raises on signature, audience, or expiry mismatch.
        """
        return authority_trust.verify_service_jwt(
            token,
            expected_issuer=from_issuer,
            expected_audience=expected_audience or self._service_name,
        )

    def verify_delegation_caller(
        self,
        token: str,
        *,
        from_issuer: str,
        expected_actor: Optional[str] = None,
    ) -> dict[str, Any]:
        """Verify an inbound delegation JWT (RFC 8693).

        Used when another service is calling on behalf of a user. `expected_actor`
        is the `act.sub` claim — the service acting as the delegate (defaults
        to `from_issuer`).
        """
        return authority_trust.verify_delegation_jwt(
            token,
            expected_issuer=from_issuer,
            expected_audience=self._service_name,
            expected_actor=expected_actor or from_issuer,
        )
