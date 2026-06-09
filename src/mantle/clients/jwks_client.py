"""JWKS resolver for Mantle → Origin token verification.

Phase C: Origin's JWKS lives inline in the platform authority manifest. There
is no HTTP fetch — services read the manifest from disk via
`core.authority_trust`, which is loaded once at lifespan startup and refreshed
on `authority.updated` events. This module preserves the historic
`get_jwks_client().get_key(kid)` API so existing callers don't need to change.

Rotation: when the operator patches the authority artifact (e.g. to add a new
JWK with a fresh kid), Mantle receives the `authority.updated` event and calls
`reset_jwks_client()` (or `core.authority_trust.reload_authority_manifest()`).
The next `get_key(kid)` call resolves the new kid.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from kernel import authority_trust

logger = logging.getLogger(__name__)


class JwksClient:
    """Resolves Origin-signed token kids against the inline JWKS in the authority manifest."""

    def __init__(self, *_, **__) -> None:
        # Backward-compat positional args (origin_uri, cache_ttl_s) accepted but ignored.
        self._lock = threading.Lock()

    def get_key(self, kid: str) -> Optional[dict]:
        """Return the JWK dict for a given kid, or None if not found.

        Looks up Origin's inline JWKS in the platform authority manifest.
        """
        with self._lock:
            try:
                manifest = authority_trust.get_authority_manifest()
            except FileNotFoundError:
                logger.warning("Authority manifest missing — JWKS resolution unavailable")
                return None
            try:
                jwks = manifest.get_jwks("origin")
            except KeyError:
                logger.warning("No `origin` trust anchor in authority manifest")
                return None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    return key
            return None


_jwks_client: Optional[JwksClient] = None


def get_jwks_client() -> JwksClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = JwksClient()
    return _jwks_client


def reset_jwks_client() -> None:
    """Test hook + rotation entry point."""
    global _jwks_client
    _jwks_client = None
    authority_trust.reset_authority_manifest_for_tests()
