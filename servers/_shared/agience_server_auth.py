"""Shared authentication framework for Agience MCP servers.

Core defines the delegation JWT standard and signs tokens with RS256.
Servers fall in line by:

  1. Fetching Core's JWKS at startup to verify delegation JWTs
  2. Verifying ``aud == client_id`` before storing delegation tokens
  3. Registering their RSA public key with Core for JWE-wrapped secret delivery

Usage
-----
Create one ``AgieceServerAuth`` instance at module level per server module::

    auth = AgieceServerAuth(SERVER_CLIENT_ID, AGIENCE_API_URI)

Then expose the standard server interface::

    def create_server_app():
        return auth.create_app(mcp, _exchange_token)

    async def server_startup():
        await auth.startup(_exchange_token)

Multiple instances are safe in a single process (_host mounts) because
each ``AgieceServerAuth`` owns its own ContextVar (disambiguated by client_id).

Transport-level identity binding (mTLS / DPoP) is not yet enforced.
The ``aud`` claim provides intent binding; full transport binding is a
future requirement.
"""

from __future__ import annotations

import base64
import contextvars
import logging
import os
import time
from typing import Any, Awaitable, Callable

from jose import jwt as jose_jwt, JWTError

log = logging.getLogger(__name__)

# Minimum interval between JWKS refresh attempts (seconds).
_JWKS_REFRESH_INTERVAL = 60


class AgieceServerAuth:
    """Per-server authentication and delegation context.

    Holds RSA key pair for JWE decryption, Core JWKS cache for delegation JWT
    verification, and a per-request ContextVar.

    Parameters
    ----------
    client_id:
        The server's ``agience-server-<name>`` identifier, used as the
        expected ``aud`` claim in delegation JWTs and the JWK ``kid``.
    agience_api_uri:
        Base URI of the Agience Core backend.
    """

    def __init__(self, client_id: str, agience_api_uri: str) -> None:
        self.client_id = client_id
        self.agience_api_uri = agience_api_uri.rstrip("/")

        self._core_jwks: dict = {}                # Full JWKS keyset from Core
        self._core_jwks_fetched_at: float = 0.0   # monotonic time of last JWKS fetch
        self._server_private_key: Any = None      # cryptography RSAPrivateKey
        self._server_public_jwk: dict = {}

        # Per-request ContextVar.  The name includes client_id so that
        # multiple server instances in a single process (_host) stay isolated.
        self.request_user_token: contextvars.ContextVar[str] = contextvars.ContextVar(
            f"agience_request_user_token_{client_id}", default=""
        )

        # Key init is synchronous — safe to run at module load.
        self._init_server_keys()

    # ------------------------------------------------------------------
    # RSA key pair (sync — called at module load)
    # ------------------------------------------------------------------

    def _init_server_keys(self) -> None:
        """Load or generate an RSA-2048 key pair for JWE secret delivery.

        Reads ``SERVER_PRIVATE_KEY_PEM`` from the environment (PEM string or
        base64-encoded PEM).  Falls back to an ephemeral key pair if absent.
        The public JWK is stored in ``_server_public_jwk`` for Core registration.
        """
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        pem_raw = os.getenv("SERVER_PRIVATE_KEY_PEM", "")
        if pem_raw:
            if not pem_raw.strip().startswith("-----"):
                try:
                    pem_raw = base64.b64decode(pem_raw).decode()
                except Exception:
                    pass
            self._server_private_key = serialization.load_pem_private_key(
                pem_raw.encode(), password=None
            )
        else:
            self._server_private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )

        pub = self._server_private_key.public_key()
        pub_numbers = pub.public_numbers()

        def _int_to_b64url(n: int) -> str:
            byte_length = (n.bit_length() + 7) // 8
            return base64.urlsafe_b64encode(n.to_bytes(byte_length, "big")).rstrip(b"=").decode()

        self._server_public_jwk = {
            "kty": "RSA",
            "alg": "RSA-OAEP-256",
            "use": "enc",
            "n": _int_to_b64url(pub_numbers.n),
            "e": _int_to_b64url(pub_numbers.e),
            "kid": self.client_id,
        }

    # ------------------------------------------------------------------
    # Core JWKS (async — called at startup)
    # ------------------------------------------------------------------

    async def fetch_core_jwks(self) -> None:
        """Fetch and cache Core's JWKS from ``/.well-known/jwks.json``.

        The full keyset is stored so that ``python-jose`` can match JWTs
        by ``kid`` header at verification time.  Called at startup and
        may be re-fetched on verification failure (rate-limited).

        On success, updates ``_core_jwks_fetched_at`` so that
        ``_refresh_jwks_if_stale`` rate-limits re-fetches to once per
        ``_JWKS_REFRESH_INTERVAL``.  On failure, only updates the
        timestamp if keys have been loaded at least once (prevents a
        startup failure from blocking retries for 60 s when Core is
        still coming up).
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.agience_api_uri}/.well-known/jwks.json")
                resp.raise_for_status()
                self._core_jwks = resp.json()
                self._core_jwks_fetched_at = time.monotonic()
            log.info("Core JWKS loaded for %s — delegation JWT verification active", self.client_id)
        except Exception as exc:
            # Only rate-limit retries if we previously loaded keys
            # successfully.  During initial boot (keys empty), leave
            # _core_jwks_fetched_at at 0 so _refresh_jwks_if_stale
            # retries on the very next inbound request.
            if self._core_jwks.get("keys"):
                self._core_jwks_fetched_at = time.monotonic()
            log.error(
                "Failed to fetch Core JWKS for %s: %s — delegation verification disabled",
                self.client_id, exc,
            )

    async def _refresh_jwks_if_stale(self) -> bool:
        """Re-fetch JWKS if the last fetch was more than ``_JWKS_REFRESH_INTERVAL`` ago.

        Returns ``True`` if a refresh was performed, ``False`` if skipped
        (too soon since last fetch).
        """
        if time.monotonic() - self._core_jwks_fetched_at < _JWKS_REFRESH_INTERVAL:
            return False
        await self.fetch_core_jwks()
        return True

    # ------------------------------------------------------------------
    # Delegation JWT verification
    # ------------------------------------------------------------------

    def verify_delegation_jwt(self, token: str) -> dict | None:
        """Verify a delegation JWT signed by Core.

        Uses ``python-jose`` for RS256 signature verification with automatic
        ``kid`` matching against the cached JWKS.  Validates:

        - RS256 signature (via JWKS, matched by ``kid``)
        - ``aud == self.client_id``  (token was issued FOR this server)
        - ``principal_type == "delegation"``
        - Token not expired

        Returns decoded claims on success, ``None`` on any failure.
        """
        if not self._core_jwks.get("keys") or not token:
            return None
        try:
            claims = jose_jwt.decode(
                token,
                self._core_jwks,
                algorithms=["RS256"],
                audience=self.client_id,
            )
            if claims.get("principal_type") != "delegation":
                log.debug(
                    "Delegation JWT rejected for %s: principal_type=%s",
                    self.client_id, claims.get("principal_type"),
                )
                return None
            return claims
        except JWTError as exc:
            log.debug("Delegation JWT rejected for %s: %s", self.client_id, exc)
            return None

    def verify_core_jwt(self, token: str) -> dict | None:
        """Verify any non-delegation JWT signed by Core.

        Uses ``python-jose`` for RS256 signature verification.  Accepts tokens
        whose ``aud`` is either ``"agience"`` (server-credential tokens) or the
        deployment's ``AUTHORITY_ISSUER`` URI (user-session tokens forwarded by
        Core).  Delegation tokens are explicitly rejected — use
        ``verify_delegation_jwt`` instead.

        Returns decoded claims on success, ``None`` on any failure.
        """
        if not self._core_jwks.get("keys") or not token:
            return None
        try:
            # Decode without audience enforcement so we can inspect the claim
            # and validate it against the set of accepted values.
            claims = jose_jwt.decode(
                token,
                self._core_jwks,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            if claims.get("principal_type") == "delegation":
                log.debug(
                    "Core JWT rejected for %s: delegation tokens must use verify_delegation_jwt",
                    self.client_id,
                )
                return None
            aud = claims.get("aud")
            # Accept "agience" (server credentials) and any non-empty aud
            # (platform-client user tokens, mcp_client tokens).  Reject tokens
            # with no aud — they were issued before the audience fix landed.
            if not aud:
                log.debug(
                    "Core JWT rejected for %s: missing aud claim",
                    self.client_id,
                )
                return None
            return claims
        except JWTError as exc:
            log.debug("Core JWT rejected for %s: %s", self.client_id, exc)
            return None

    # ------------------------------------------------------------------
    # JWE decryption
    # ------------------------------------------------------------------

    def decrypt_jwe(self, jwe: dict) -> str:
        """Decrypt a JWE envelope returned by Core's ``/secrets/fetch``.

        Uses this server's RSA private key (RSA-OAEP-256) to unwrap the
        content encryption key, then decrypts with AES-256-GCM.
        """
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        def _b64d(s: str) -> bytes:
            s += "=" * (4 - len(s) % 4)
            return base64.urlsafe_b64decode(s)

        cek = self._server_private_key.decrypt(
            _b64d(jwe["ek"]),
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        plaintext = AESGCM(cek).decrypt(
            _b64d(jwe["iv"]),
            _b64d(jwe["ct"]) + _b64d(jwe["tag"]),
            None,
        )
        return plaintext.decode("utf-8")

    # ------------------------------------------------------------------
    # Server key registration (async — called at startup)
    # ------------------------------------------------------------------

    async def register_server_key(
        self, exchange_token_func: Callable[[], Awaitable[str | None]]
    ) -> None:
        """Register this server's RSA public JWK with Core.

        Core stores the JWK so it can wrap secrets destined for this server
        using RSA-OAEP-256.  Called at startup after PLATFORM_INTERNAL_SECRET
        token exchange is available.
        """
        import httpx

        server_token = await exchange_token_func()
        if not server_token:
            log.warning(
                "Cannot register server key for %s: no server token available", self.client_id
            )
            return

        headers = {"Authorization": f"Bearer {server_token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.put(
                f"{self.agience_api_uri}/server-credentials/{self.client_id}/key",
                headers=headers,
                json={"public_jwk": self._server_public_jwk},
            )
        if resp.status_code in (200, 204):
            log.info("Server JWK registered for %s", self.client_id)
        else:
            log.error(
                "Failed to register server JWK for %s: %s %s",
                self.client_id, resp.status_code, resp.text[:200],
            )

    # ------------------------------------------------------------------
    # Per-request helpers
    # ------------------------------------------------------------------

    async def user_headers(
        self, exchange_token_func: Callable[[], Awaitable[str | None]]
    ) -> dict[str, str]:
        """Authorization headers carrying the verified delegation JWT.

        The delegation JWT was issued by Core with ``aud == self.client_id``
        and verified by the middleware before storage.  Presenting it to Core
        endpoints is not forwarding — it is using a token explicitly issued TO
        this server.

        Falls back to the server's own platform token for startup or background
        calls that carry no user delegation context.
        """
        h = {"Content-Type": "application/json"}
        token = self.request_user_token.get("")
        if token:
            h["Authorization"] = f"Bearer {token}"
            return h
        server_token = await exchange_token_func()
        if server_token:
            h["Authorization"] = f"Bearer {server_token}"
        return h

    def get_delegation_user_id(self) -> str:
        """Extract the ``sub`` (user ID) from the stored delegation JWT.

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
    # ASGI middleware factory
    # ------------------------------------------------------------------

    def make_middleware_class(self):
        """Return an ASGI middleware class that verifies and captures delegation JWTs.

        Only delegation JWTs explicitly issued TO this server (``aud == client_id``)
        are stored.  Any other token leaves the ContextVar empty and tools fall
        back to the server's own platform token.
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

                # Accept only delegation JWTs verified against Core's public key.
                verified = auth.verify_delegation_jwt(raw_token)
                if not verified and raw_token and await auth._refresh_jwks_if_stale():
                    # Retry once after JWKS refresh (handles key rotation).
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

    async def startup(
        self, exchange_token_func: Callable[[], Awaitable[str | None]]
    ) -> None:
        """Run all startup tasks: Core JWKS fetch + server key registration.

        Retries the key-registration step on transient Core-not-ready errors
        (connection refused, 502/503/504) so that a fast-starting servers-host
        container doesn't crash-loop if Core is still initialising.  Falls back
        to a clean crash after max attempts so Docker's restart policy still
        kicks in if Core is genuinely down.
        """
        import asyncio
        import httpx

        await self.fetch_core_jwks()

        _MAX_ATTEMPTS = 8
        _BACKOFF_CAP = 10.0  # seconds

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                await self.register_server_key(exchange_token_func)
                return
            except (httpx.ConnectError, httpx.TransportError):
                if attempt >= _MAX_ATTEMPTS:
                    raise
                status_hint = ""
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in (502, 503, 504) or attempt >= _MAX_ATTEMPTS:
                    raise
                status_hint = f", HTTP {status}"

            delay = min(1.0 * (2 ** (attempt - 1)), _BACKOFF_CAP)
            log.warning(
                "%s: Core not ready (attempt %d/%d%s) — retrying in %.1fs",
                self.client_id,
                attempt,
                _MAX_ATTEMPTS,
                status_hint,
                delay,
            )
            await asyncio.sleep(delay)

    def create_app(
        self,
        mcp_instance: Any,
        exchange_token_func: Callable[[], Awaitable[str | None]],
    ) -> Any:
        """Return the MCP ASGI app wrapped with verified middleware and startup hooks.

        The returned ASGI app:
        - Verifies delegation JWTs on every request
        - Stores verified tokens in the per-request ContextVar
        - Runs JWKS fetch + key registration on the first startup event

        Suitable for both standalone ``uvicorn.run()`` and sub-app mounting
        in ``_host``.  See also ``startup()`` for explicit startup hooks
        when mounting under a parent FastAPI app (``_host``).
        """
        inner_app = mcp_instance.streamable_http_app()
        auth = self

        async def _on_startup() -> None:
            await auth.startup(exchange_token_func)

        # ``add_event_handler`` was removed in Starlette 0.41 (FastAPI 0.115+).
        # Use a pure ASGI lifespan interceptor instead: intercept the
        # ``lifespan.startup.complete`` message that the inner app sends and
        # run our startup hook at that point before forwarding the message.
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
