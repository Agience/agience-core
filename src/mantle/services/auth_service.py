"""Mantle auth service — verifier-only after 1.1e.

Origin owns all token issuance, password hashing, and OAuth flows. Mantle
retains:

- `verify_token` — JWT verification against Origin's public key (switches
  to JWKS-over-HTTP in 1.3).
- `verify_api_key` — raw `agc_xxx` Bearer verification via Origin's
  `/api-keys/verify` (HTTP).
- `verify_nonce` — stateless HMAC challenge-token validation.
- `hash_api_key` / `generate_api_key` — used by `services/grant_service.py`
  and the deprecated card-key rotation in `services/workspace_service.py`.
- `OAuth2Error` constants — used by gate/api-key error paths.
- `NONCE_TTL_SECONDS` / `JWT_ALGORITHM` / `ACCESS_TOKEN_EXPIRE_HOURS`.

All issuance helpers (`create_jwt_token`, `hash_password`, `is_person_allowed`,
etc.) moved to Origin alongside their last callers in 1.1e.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from arango.database import StandardDatabase
from jose import JWTError, jwt

from kernel import config
from entities.api_key import APIKey as APIKeyEntity

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "RS256"
ACCESS_TOKEN_EXPIRE_HOURS = 12
NONCE_TTL_SECONDS = 1800


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------
def verify_token(token: str, expected_audience: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Verify and decode an incoming JWT.

    Phase C dispatch by the unverified `iss` claim:
    - `iss ∈ {"mantle", "chorus", "origin"}`  → kernel-service mutual JWT.
      Verified against the inline JWKS for that service in the platform
      authority manifest via `core.authority_trust`.
    - Anything else (typically `iss == AUTHORITY_ISSUER` URL) → user / legacy
      token signed by Origin. Verified via `clients.jwks_client` (which
      also reads from the authority manifest).
    """
    try:
        unverified = jwt.get_unverified_claims(token)
    except JWTError:
        return None

    iss = unverified.get("iss", "")

    if iss in ("mantle", "chorus", "origin"):
        from kernel.authority_trust import verify_jwt as _verify_via_authority

        try:
            payload = _verify_via_authority(
                token,
                expected_issuer_service=iss,
                expected_audience=expected_audience,
                expected_issuer_claim=iss,
            )
        except (KeyError, JWTError):
            return None
        exp = payload.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            return None
        return payload

    # User token signed by Origin: verify via the JWKS resolved through the
    # authority manifest (jwks_client is the bridge).
    try:
        kid = jwt.get_unverified_header(token).get("kid", "")
    except JWTError as exc:
        logger.warning("verify_token: header parse failed: %r", exc)
        return None

    if not kid:
        logger.warning("verify_token: token has no kid header")
        return None

    from clients.jwks_client import get_jwks_client

    jwk = get_jwks_client().get_key(kid)
    if jwk is None:
        logger.warning("verify_token: kid %r not found in authority manifest", kid)
        return None

    try:
        decode_kwargs: dict = {
            "algorithms": [JWT_ALGORITHM],
            "issuer": config.AUTHORITY_ISSUER,
            "options": {"verify_iss": True},
        }
        if expected_audience is not None:
            decode_kwargs["audience"] = expected_audience
        else:
            decode_kwargs["options"]["verify_aud"] = False
        payload = jwt.decode(token, jwk, **decode_kwargs)
        exp = payload.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            logger.warning("verify_token: token expired (exp=%s, now=%s)", exp, datetime.now(timezone.utc).timestamp())
            return None
        return payload
    except JWTError as exc:
        logger.warning("verify_token: jwt.decode failed: %r (expected_iss=%s, expected_aud=%s)", exc, config.AUTHORITY_ISSUER, expected_audience)
        return None


def verify_api_key(db: StandardDatabase, api_key: str) -> Optional[APIKeyEntity]:
    """Verify a raw `agc_xxx` token via Origin (1.1c onward).

    The `db` parameter is unused — kept for signature compat with callers
    in `services.dependencies.resolve_auth`. Origin owns the api_keys table.
    """
    del db
    from clients.origin_client import get_origin_client

    result = get_origin_client().verify_api_key(api_key)
    if result is None:
        return None
    api_key_entity, _grants = result
    return api_key_entity


def verify_nonce(
    token: str,
    key_id: str,
    artifact_id: str,
    secret: str,
    ttl_seconds: int = NONCE_TTL_SECONDS,
) -> bool:
    if not secret or not token:
        return False
    try:
        padding = "=" * (4 - len(token) % 4)
        decoded = base64.urlsafe_b64decode(token + padding).decode("utf-8")
        parts = decoded.split(":", 3)
        if len(parts) != 4:
            return False
        ts_str, nonce_artifact_id, nonce_key_id, sig = parts
        ts = int(ts_str)
    except Exception:
        return False
    if nonce_artifact_id != artifact_id or nonce_key_id != key_id:
        return False
    if int(time.time()) - ts > ttl_seconds:
        return False
    expected_payload = f"{ts_str}:{artifact_id}:{key_id}"
    expected_sig = hmac.new(
        secret.encode("utf-8"), expected_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return secrets.compare_digest(sig, expected_sig)


# ---------------------------------------------------------------------------
# API key helpers — small, stateless, Mantle-owned
# ---------------------------------------------------------------------------
def generate_api_key() -> str:
    return f"agc_{secrets.token_bytes(16).hex()}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# OAuth2 error constants — used by error responses in gate / api-key paths.
# ---------------------------------------------------------------------------
class OAuth2Error:
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED_CLIENT = "unauthorized_client"
    ACCESS_DENIED = "access_denied"
    UNSUPPORTED_RESPONSE_TYPE = "unsupported_response_type"
    INVALID_SCOPE = "invalid_scope"
    SERVER_ERROR = "server_error"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    INVALID_CLIENT = "invalid_client"
    INVALID_GRANT = "invalid_grant"
    UNSUPPORTED_GRANT_TYPE = "unsupported_grant_type"
