"""Origin auth verification (Postgres-backed).

Mirrors the verifier shape used in Mantle — but reads api_keys from Postgres
rather than Arango. JWT verification uses Origin's local public key (1.1a). In
1.3 Mantle's verifier switches to JWKS-over-HTTP; Origin's stays local.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from kernel import config
from kernel.key_manager import get_public_key_pem
from origin.db import api_keys as db_api_keys
from origin.models.api_key import ApiKey

JWT_ALGORITHM = "RS256"


def verify_token(token: str, expected_audience: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Verify and decode an incoming JWT.

    Dispatches by the unverified `iss` claim:
    - `iss ∈ {"mantle", "chorus"}`  → kernel-service mutual JWT (Phase C). Verified
      against the inline JWKS in the platform authority manifest via
      `core.authority_trust`.
    - Anything else (typically `iss == AUTHORITY_ISSUER` URL) → token issued by
      Origin itself. Verified with Origin's local public key.
    """
    try:
        unverified = jwt.get_unverified_claims(token)
    except JWTError:
        return None

    iss = unverified.get("iss", "")

    # Phase C: kernel-service mutual JWT
    if iss in ("mantle", "chorus"):
        from kernel.authority_trust import verify_jwt as _verify_via_authority
        from jose.exceptions import JWTError as _JoseJWTError

        try:
            payload = _verify_via_authority(
                token,
                expected_issuer_service=iss,
                expected_audience=expected_audience,
                expected_issuer_claim=iss,
            )
        except (KeyError, _JoseJWTError):
            return None
        exp = payload.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            return None
        return payload

    # Legacy / standard: Origin-signed token
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

        payload = jwt.decode(token, get_public_key_pem(), **decode_kwargs)
        exp = payload.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            return None
        return payload
    except JWTError:
        return None


def verify_api_key(db: Session, api_key: str) -> Optional[ApiKey]:
    """Verify a raw `agc_xxx` API key. Returns the ORM entity if valid.

    Side effect: bumps `last_used_at` on success.
    """
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    entity = db_api_keys.get_by_hash(db, key_hash)
    if entity is None:
        return None
    if not entity.is_active:
        return None
    if entity.expires_at is not None:
        exp = entity.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp:
            return None
    db_api_keys.update_last_used(db, entity.id)
    return entity


def verify_nonce(
    token: str,
    key_id: str,
    artifact_id: str,
    secret: str,
    ttl_seconds: int = 1800,
) -> bool:
    """Verify a nonce token issued by `auth_service.issue_nonce`.

    Returns False (not raise) on any failure — caller decides the HTTP status.
    """
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
    if int(datetime.now(timezone.utc).timestamp()) - ts > ttl_seconds:
        return False

    expected_payload = f"{ts_str}:{artifact_id}:{key_id}"
    expected_sig = hmac.new(
        secret.encode("utf-8"), expected_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sig, expected_sig)
