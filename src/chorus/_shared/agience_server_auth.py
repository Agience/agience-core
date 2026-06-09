"""Shared authentication framework for Chorus MCP persona servers.

Each persona running inside the Chorus container shares one service identity
(`chorus.private.pem`, written by the init container into KEYS_DIR). The persona's
`client_id` distinguishes who is calling — it lands in the `sub` claim of every
outbound JWT, while `iss` always reads `chorus`.

Verification of inbound delegation JWTs (Mantle → Chorus, RFC 8693) and inbound
user JWTs (Origin → Chorus) flows through `core.authority_trust`, which reads
the inline JWKS from the platform authority manifest. There is no HTTP fetch
of `/.well-known/jwks.json`; the manifest is on disk.

Usage
-----
Create one ``AgieceServerAuth`` instance at module level per persona::

    auth = AgieceServerAuth(SERVER_CLIENT_ID, AGIENCE_API_URI)

Then expose the standard server interface::

    def create_server_app():
        return auth.create_app(mcp)

    async def server_startup():
        await auth.startup()

Multiple instances are safe in a single process (the unified ``chorus`` host) —
each ``AgieceServerAuth`` owns its own ContextVar (disambiguated by client_id)
and self-identifies via its `client_id`.

Phase C trust model:
- Service identity loaded once via `core.service_identity.init_service_identity("chorus")`
  at process startup (call from `chorus/server.py`'s lifespan, before any persona module loads).
- Every outbound JWT signed with `chorus.private.pem` (RS256, kid=chorus-1).
- Every inbound JWT verified against the relevant service's inline JWKS in the
  authority manifest.
- No `PLATFORM_INTERNAL_SECRET`, no HTTP token exchange, no JWKS fetch.

Transport-level identity binding (mTLS / DPoP) is not yet enforced. The `aud`
claim provides intent binding; full transport binding is a future requirement.
"""

from __future__ import annotations

import base64
import contextvars
import logging
from typing import Any

from jose import jwt as jose_jwt, JWTError

from kernel import service_identity
from kernel.authority_trust import (
    verify_delegation_jwt as _verify_delegation_jwt,
    verify_jwt as _verify_jwt,
)

log = logging.getLogger(__name__)


class AgieceServerAuth:
    """Per-persona authentication and delegation context.

    Holds a per-request ContextVar for the inbound delegation JWT, exposes
    helpers for signing outbound kernel JWTs (via the chorus service identity),
    and provides ASGI middleware that verifies inbound delegation JWTs against
    the platform authority manifest.

    Parameters
    ----------
    client_id:
        The persona's ``agience-server-<name>`` identifier, used as the
        expected ``aud`` claim on inbound delegation JWTs and as ``sub`` on
        outbound kernel JWTs signed by this persona.
    agience_api_uri:
        Base URI of the Mantle backend (kept for tools that need to make REST
        calls to Mantle).
    """

    def __init__(self, client_id: str, agience_api_uri: str) -> None:
        self.client_id = client_id
        self.agience_api_uri = agience_api_uri.rstrip("/")

        # Per-request ContextVar — name includes client_id so multiple personas
        # mounted in one process stay isolated.
        self.request_user_token: contextvars.ContextVar[str] = contextvars.ContextVar(
            f"agience_request_user_token_{client_id}", default=""
        )

    # ------------------------------------------------------------------
    # Inbound JWT verification (delegation, user)
    # ------------------------------------------------------------------

    def verify_delegation_jwt(self, token: str) -> dict | None:
        """Verify a delegation JWT issued by Mantle with `aud == self.client_id`.

        Validates:
        - RS256 signature against Mantle's inline JWKS in the authority manifest
        - `iss == "mantle"`
        - `aud == self.client_id`
        - `principal_type == "delegation"`
        - `act.sub == "mantle"`
        - Token not expired

        Returns decoded claims on success, ``None`` on any failure.
        """
        if not token:
            return None
        try:
            return _verify_delegation_jwt(
                token,
                expected_issuer="mantle",
                expected_audience=self.client_id,
                expected_actor="mantle",
            )
        except (KeyError, JWTError) as exc:
            log.debug("Delegation JWT rejected for %s: %s", self.client_id, exc)
            return None

    def verify_user_jwt(self, token: str) -> dict | None:
        """Verify a user-token JWT issued by Origin (non-delegation).

        Used by tools that need to confirm a user identity from a forwarded
        bearer token. Audience is variable (per-OAuth-client), so the caller
        gets the decoded claims and inspects `aud` itself.

        Returns decoded claims on success, ``None`` on any failure.
        """
        if not token:
            return None
        try:
            claims = _verify_jwt(token, expected_issuer_service="origin")
            if claims.get("principal_type") == "delegation":
                # Delegation tokens must use verify_delegation_jwt — they have
                # a different aud and require the actor check.
                log.debug(
                    "User JWT rejected for %s: delegation tokens must use verify_delegation_jwt",
                    self.client_id,
                )
                return None
            if not claims.get("aud"):
                log.debug("User JWT rejected for %s: missing aud claim", self.client_id)
                return None
            return claims
        except (KeyError, JWTError) as exc:
            log.debug("User JWT rejected for %s: %s", self.client_id, exc)
            return None

    # Back-compat alias — the previous API used this name. Equivalent semantics.
    def verify_core_jwt(self, token: str) -> dict | None:
        return self.verify_user_jwt(token)

    # ------------------------------------------------------------------
    # Outbound JWT signing (this persona → Mantle or other services)
    # ------------------------------------------------------------------

    def sign_self_jwt(self, audience: str = "mantle", ttl_seconds: int = 300) -> str:
        """Sign a service JWT identifying this persona to a peer service.

        Claims:
            iss = "chorus"            (service identity is the chorus container)
            sub = self.client_id      (persona-specific identity)
            aud = audience            (peer service: usually "mantle")
            principal_type = "service"
            iat / exp = now / now+ttl

        Returns the encoded JWT string.
        """
        return service_identity.sign_service_jwt(
            audience=audience,
            additional_claims={"sub": self.client_id, "client_id": self.client_id},
            ttl_seconds=ttl_seconds,
        )

    # ------------------------------------------------------------------
    # Per-request header helpers
    # ------------------------------------------------------------------

    def headers(self, audience: str = "mantle") -> dict[str, str]:
        """Return outbound REST headers carrying this persona's signed kernel JWT."""
        return {
            "Authorization": f"Bearer {self.sign_self_jwt(audience=audience)}",
            "Content-Type": "application/json",
        }

    def user_headers(self, audience: str = "mantle") -> dict[str, str]:
        """Outbound REST headers carrying the verified inbound delegation JWT.

        The middleware captures and verifies the inbound delegation token before
        storing it in the ContextVar — presenting it to Mantle endpoints is using
        a token explicitly issued FOR this persona, not forwarding.

        Falls back to ``self.headers()`` (the persona's own kernel JWT) when
        there is no user delegation context — startup tasks, background work,
        and direct server-to-server calls land here.
        """
        h = {"Content-Type": "application/json"}
        delegated = self.request_user_token.get("")
        if delegated:
            h["Authorization"] = f"Bearer {delegated}"
            return h
        return self.headers(audience=audience)

    def get_delegation_user_id(self) -> str:
        """Extract the `sub` (user ID) from the stored delegation JWT.

        Returns ``"anonymous"`` when no delegation context is active.
        """
        token = self.request_user_token.get("")
        if not token:
            return "anonymous"
        try:
            claims = jose_jwt.get_unverified_claims(token)
            return claims.get("sub", "anonymous")
        except JWTError:
            return "anonymous"

    # ------------------------------------------------------------------
    # ASGI middleware
    # ------------------------------------------------------------------

    def make_middleware_class(self):
        """Return an ASGI middleware class that verifies and captures delegation JWTs.

        Only delegation JWTs explicitly issued TO this persona (`aud == client_id`)
        are stored. Any other token leaves the ContextVar empty and tools fall
        back to the persona's own kernel JWT.
        """
        auth = self

        class UserTokenMiddleware:
            def __init__(self, inner_app: Any) -> None:
                self._app = inner_app

            async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
                if scope["type"] != "http":
                    await self._app(scope, receive, send)
                    return

                hdrs = dict(scope.get("headers", []))
                raw_auth = hdrs.get(b"authorization", b"").decode()
                raw_token = raw_auth[7:].strip() if raw_auth.lower().startswith("bearer ") else ""

                verified = auth.verify_delegation_jwt(raw_token)
                tok = auth.request_user_token.set(raw_token if verified else "")
                try:
                    await self._app(scope, receive, send)
                finally:
                    auth.request_user_token.reset(tok)

        return UserTokenMiddleware

    # ------------------------------------------------------------------
    # Startup + app factory
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Run startup tasks for this persona.

        The chorus host's lifespan calls `init_service_identity("chorus")`
        before any persona module loads. If that hasn't happened, this raises
        — no silent lazy-init.
        """
        service_identity.get_service_identity()
        log.info("AgieceServerAuth ready for %s (chorus identity, kid=chorus-1)", self.client_id)

    def create_app(self, mcp_instance: Any) -> Any:
        """Return the MCP ASGI app wrapped with verifying middleware and startup hook.

        The returned ASGI app:
        - Verifies delegation JWTs on every request
        - Stores verified tokens in the per-request ContextVar
        - Runs `self.startup()` on lifespan startup

        Suitable for both standalone ``uvicorn.run()`` and sub-app mounting in
        the unified chorus host.
        """
        inner_app = mcp_instance.streamable_http_app()
        auth = self

        async def _on_startup() -> None:
            await auth.startup()

        # Pure ASGI lifespan interceptor — runs `_on_startup` after the inner
        # app reports `lifespan.startup.complete`, before forwarding the message.
        class _LifespanWrapper:
            def __init__(self, app: Any) -> None:
                self._app = app

            async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
                if scope["type"] != "lifespan":
                    await self._app(scope, receive, send)
                    return

                startup_hooked = False

                async def _patched_send(message: Any) -> None:
                    nonlocal startup_hooked
                    if (
                        isinstance(message, dict)
                        and message.get("type") == "lifespan.startup.complete"
                        and not startup_hooked
                    ):
                        startup_hooked = True
                        await _on_startup()
                    await send(message)

                await self._app(scope, receive, _patched_send)

        return self.make_middleware_class()(_LifespanWrapper(inner_app))

    # ------------------------------------------------------------------
    # Deprecated — Phase D will move JWE secret delivery elsewhere
    # ------------------------------------------------------------------

    def decrypt_jwe(self, jwe: dict) -> str:
        """JWE decryption is deferred to Phase D (secrets-as-artifacts refactor).

        The legacy flow used a per-persona RSA key registered with Origin to
        receive secret values wrapped in JWE envelopes. In the new model,
        secrets are `vnd.agience.secret+json` artifacts whose handler decrypts
        on read for authorized callers. This shim raises so callers fail fast
        if the legacy path is exercised before Phase D lands.
        """
        del jwe
        raise NotImplementedError(
            "JWE decryption removed in Phase C. Secrets become "
            "vnd.agience.secret+json artifacts in Phase D — read via the "
            "artifact API and decrypt via the type handler."
        )


# ---------------------------------------------------------------------------
# Backward-compat helpers (used by older persona signatures)
# ---------------------------------------------------------------------------

def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)
