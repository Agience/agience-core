"""Trust-anchor resolution from the platform authority manifest.

Each service loads `KEYS_DIR/authority.manifest.json` once at startup. The manifest
contains the platform issuer and per-service inline JWKS (origin / mantle / chorus).
Verification of peer-service JWTs uses these anchors directly — no HTTP fetch.

Signing of the running service's own tokens lives in `core.service_identity`.

Manifest shape (written by the init container):

    {
      "artifact_id":     "<uuid>",
      "content_type":    "application/vnd.agience.authority+json",
      "schema_version":  1,
      "issuer":          "https://platform.example.com",
      "trust_anchors": {
        "origin": { "uri": "...", "jwks": { "keys": [ { "kty": "RSA", "kid": "origin-1", ... } ] } },
        "mantle":  { "uri": "...", "jwks": { "keys": [ ... ] } },
        "chorus": { "uri": "...", "jwks": { "keys": [ ... ] } }
      },
      "bootstrap_token_hash": "<sha256-hex|null>"
    }
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

import os

from jose import jwt as jose_jwt
from jose.exceptions import JWTError

logger = logging.getLogger(__name__)

# How long a cached manifest is considered fresh. Authority updates emit an
# `authority.updated` event that consumers should subscribe to and call
# `reload_authority_manifest()` on. The TTL is a fallback for processes that
# missed the event.
DEFAULT_MANIFEST_TTL_SECONDS = 300


@dataclass
class AuthorityManifest:
    """Parsed authority manifest. Treat as immutable after load."""
    issuer: str
    trust_anchors: Dict[str, Dict[str, Any]]
    bootstrap_token_hash: Optional[str]
    artifact_id: str
    raw: Dict[str, Any] = field(repr=False)

    def get_jwks(self, service_name: str) -> Dict[str, Any]:
        """Return the inline JWKS for a service, or raise KeyError if absent."""
        anchor = self.trust_anchors.get(service_name)
        if not anchor or "jwks" not in anchor:
            raise KeyError(f"No trust anchor for service {service_name!r}")
        return anchor["jwks"]

    def get_uri(self, service_name: str) -> Optional[str]:
        """Return the deployment URI for a service, if recorded."""
        anchor = self.trust_anchors.get(service_name) or {}
        return anchor.get("uri")


_manifest: Optional[AuthorityManifest] = None
_manifest_lock = Lock()


def _manifest_path() -> Path:
    val = os.getenv("KEYS_DIR")
    if val:
        return Path(val) / "authority.manifest.json"
    from kernel import config
    return config.KEYS_DIR / "authority.manifest.json"


def load_authority_manifest() -> AuthorityManifest:
    """Read and parse the authority manifest. Idempotent; safe to call repeatedly.

    Raises FileNotFoundError if the manifest is absent — services must fail fast
    at boot if the trust map is missing. Operators re-run init to produce one.
    """
    global _manifest
    with _manifest_lock:
        if _manifest is not None:
            return _manifest

        path = _manifest_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"Authority manifest missing at {path}. "
                f"The init container generates this on first boot — re-run init or check the volume mount."
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        _manifest = AuthorityManifest(
            issuer=raw["issuer"],
            trust_anchors=raw.get("trust_anchors", {}),
            bootstrap_token_hash=raw.get("bootstrap_token_hash"),
            artifact_id=raw["artifact_id"],
            raw=raw,
        )
        logger.info(
            "Authority manifest loaded: issuer=%s anchors=%s bootstrap_token_hash=%s",
            _manifest.issuer,
            sorted(_manifest.trust_anchors.keys()),
            "present" if _manifest.bootstrap_token_hash else "cleared",
        )
        return _manifest


def get_authority_manifest() -> AuthorityManifest:
    """Return the loaded manifest, loading on first access."""
    if _manifest is None:
        return load_authority_manifest()
    return _manifest


def reload_authority_manifest() -> AuthorityManifest:
    """Force a re-read from disk. Call after `authority.updated` events.

    Keys may have rotated, the bootstrap token hash may have been cleared, etc.
    """
    global _manifest
    with _manifest_lock:
        _manifest = None
    return load_authority_manifest()


def reset_authority_manifest_for_tests() -> None:
    """Test-only hook to clear cached state between cases."""
    global _manifest
    with _manifest_lock:
        _manifest = None


# ---------------------------------------------------------------------------
# JWT verification
# ---------------------------------------------------------------------------


def verify_jwt(
    token: str,
    *,
    expected_issuer_service: str,
    expected_audience: Optional[Any] = None,
    expected_issuer_claim: Optional[str] = None,
) -> Dict[str, Any]:
    """Lower-level verification: signature against `expected_issuer_service`'s inline JWKS,
    optionally enforcing audience and issuer-claim match.

    Use this for user tokens or other JWTs where the `iss` claim doesn't match the service
    name itself (e.g. user tokens have `iss = AUTHORITY_ISSUER` URL, not "origin"). Pass
    `expected_audience=None` to skip audience verification (caller validates aud manually).

    `expected_audience` accepts a string (single) or a list of strings (matches any).

    Raises:
        KeyError    — no trust anchor for `expected_issuer_service`
        JWTError    — signature/claims invalid
    """
    manifest = get_authority_manifest()
    jwks = manifest.get_jwks(expected_issuer_service)

    # python-jose only accepts a string for `audience`. For list-of-acceptable-audiences
    # we decode without aud check, then validate manually against the list.
    audience_list = expected_audience if isinstance(expected_audience, list) else None
    audience_single = expected_audience if isinstance(expected_audience, str) else None

    options: Dict[str, Any] = {}
    if audience_list is not None or audience_single is None:
        options["verify_aud"] = False
    if expected_issuer_claim is None:
        options["verify_iss"] = False

    decode_kwargs: Dict[str, Any] = {
        "key": jwks,
        "algorithms": ["RS256"],
        "options": options,
    }
    if audience_single is not None:
        decode_kwargs["audience"] = audience_single
    if expected_issuer_claim is not None:
        decode_kwargs["issuer"] = expected_issuer_claim

    claims = jose_jwt.decode(token, **decode_kwargs)

    if audience_list is not None:
        token_aud = claims.get("aud")
        if isinstance(token_aud, str):
            if token_aud not in audience_list:
                from jose.exceptions import JWTError
                raise JWTError(f"audience {token_aud!r} not in accepted list {audience_list!r}")
        elif isinstance(token_aud, list):
            if not any(a in audience_list for a in token_aud):
                from jose.exceptions import JWTError
                raise JWTError(f"audience {token_aud!r} not in accepted list {audience_list!r}")
        else:
            from jose.exceptions import JWTError
            raise JWTError("token has no audience claim")

    return claims


def verify_service_jwt(
    token: str,
    *,
    expected_issuer: str,
    expected_audience: str,
) -> Dict[str, Any]:
    """Verify a peer-service JWT using the inline JWKS for `expected_issuer`.

    The `iss` claim must equal the service name (origin / mantle / chorus). For user tokens
    where `iss` is the platform URL, use `verify_jwt` directly.

    Returns the decoded claims dict on success.

    Raises:
        KeyError    — no trust anchor for the expected issuer (manifest mismatch)
        JWTError    — signature/claims invalid (wrong sig, expired, wrong aud, etc.)
    """
    return verify_jwt(
        token,
        expected_issuer_service=expected_issuer,
        expected_audience=expected_audience,
        expected_issuer_claim=expected_issuer,
    )


def verify_delegation_jwt(
    token: str,
    *,
    expected_issuer: str,
    expected_audience: str,
    expected_actor: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify a delegation JWT (RFC 8693) using the inline JWKS for `expected_issuer`.

    Performs the same signature/aud/iss check as `verify_service_jwt`, plus:
    - Confirms `principal_type == "delegation"`.
    - If `expected_actor` is provided, confirms `act.sub` matches.

    The caller is responsible for further checking `sub` (the user being delegated
    to) against their own grant model. This function only validates the envelope.
    """
    claims = verify_service_jwt(
        token,
        expected_issuer=expected_issuer,
        expected_audience=expected_audience,
    )
    if claims.get("principal_type") != "delegation":
        raise JWTError(
            f"principal_type expected 'delegation', got {claims.get('principal_type')!r}"
        )
    if expected_actor is not None:
        actor = (claims.get("act") or {}).get("sub")
        if actor != expected_actor:
            raise JWTError(f"act.sub expected {expected_actor!r}, got {actor!r}")
    return claims
