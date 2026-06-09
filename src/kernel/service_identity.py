"""Per-service identity and signing.

Each service (origin, mantle, chorus) holds its own RSA private key in `KEYS_DIR`.
This module loads it once at startup and exposes the API for signing service-to-service
JWTs. Verification of peer-service JWTs lives in `core.authority_trust`.

Key files (written by the init container):
  KEYS_DIR/origin.private.pem    only origin reads this
  KEYS_DIR/mantle.private.pem     only mantle reads this
  KEYS_DIR/chorus.private.pem    only chorus reads this

Service identity contract:
  - `iss` claim equals the service name ("origin", "mantle", or "chorus")
  - `kid` claim equals "{service}-1" (matches authority manifest's JWK kid)
  - `aud` claim names the recipient service ("mantle", "chorus", "origin")
  - `principal_type` claim distinguishes payload kinds:
      - "service"      service-to-service call, no user
      - "delegation"   mantle proxying a user request to chorus (carries `act.sub`)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import serialization
import os

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jose import jwt as jose_jwt

logger = logging.getLogger(__name__)

# Service names recognized by the authority manifest. New services would extend this.
SERVICE_NAMES = ("origin", "mantle", "chorus")

# Default service-to-service JWT TTL (seconds). Short — these tokens are issued
# fresh per call. Override per-call if a longer TTL is genuinely needed.
DEFAULT_TTL_SECONDS = 300

# Delegation tokens (RFC 8693) carry user_id in `sub` and the actor in `act.sub`.
# Same TTL — delegation is per-request.
DEFAULT_DELEGATION_TTL_SECONDS = 300


@dataclass(frozen=True)
class ServiceIdentity:
    """The loaded private key + identity metadata for the running service."""
    name: str
    kid: str
    private_key: RSAPrivateKey


_loaded: Optional[ServiceIdentity] = None


def _keys_dir() -> Path:
    """Resolve the keys directory, reading KEYS_DIR env at call time so tests can monkeypatch it."""
    val = os.getenv("KEYS_DIR")
    if val:
        return Path(val)
    from kernel import config
    return config.KEYS_DIR


def init_service_identity(service_name: str) -> ServiceIdentity:
    """Load the running service's private key from disk. Idempotent.

    Call once at lifespan startup. After this returns, `get_service_identity()`
    is available process-wide.

    Raises FileNotFoundError if the expected `{service_name}.private.pem` is absent —
    services must fail fast at boot if their identity is missing.
    """
    global _loaded
    if _loaded is not None and _loaded.name == service_name:
        return _loaded

    if service_name not in SERVICE_NAMES:
        raise ValueError(f"Unknown service name {service_name!r}; expected one of {SERVICE_NAMES}")

    priv_path = _keys_dir() / f"{service_name}.private.pem"
    if not priv_path.is_file():
        raise FileNotFoundError(
            f"Service private key missing at {priv_path}. "
            f"The init container generates these on first boot — re-run init or check the volume mount."
        )

    pem = priv_path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, RSAPrivateKey):
        raise TypeError(f"{priv_path} is not an RSA private key")

    identity = ServiceIdentity(name=service_name, kid=f"{service_name}-1", private_key=key)
    _loaded = identity
    logger.info("Service identity loaded: name=%s kid=%s", identity.name, identity.kid)
    return identity


def get_service_identity() -> ServiceIdentity:
    """Return the loaded service identity. Raises if `init_service_identity` was not called."""
    if _loaded is None:
        raise RuntimeError(
            "Service identity not initialized — call init_service_identity(service_name) at lifespan startup."
        )
    return _loaded


def reset_service_identity_for_tests() -> None:
    """Test-only hook to clear the module-level identity between cases."""
    global _loaded
    _loaded = None


def sign_service_jwt(
    *,
    audience: str,
    additional_claims: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    issuer_override: Optional[str] = None,
) -> str:
    """Sign a service-to-service JWT with the running service's private key.

    Default claims:
        iss = service name
        sub = service name        (service-to-service is self-as-subject)
        aud = audience
        principal_type = "service"
        iat = now
        exp = now + ttl_seconds
        kid in header

    Pass additional_claims to add fields (e.g. scopes, request_id). Existing
    keys win — additional_claims cannot override the default claims above.

    `issuer_override` is for narrow cases where the service speaks on behalf of a
    different identity (rare; only used during bootstrap-token claim where Origin
    speaks as itself but binds to the deployment's authority issuer). Otherwise
    use the default.
    """
    identity = get_service_identity()
    now = int(time.time())
    iss = issuer_override or identity.name
    claims: Dict[str, Any] = {
        "iss": iss,
        "sub": identity.name,
        "aud": audience,
        "principal_type": "service",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    if additional_claims:
        for k, v in additional_claims.items():
            claims.setdefault(k, v)

    pem = identity.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return jose_jwt.encode(claims, pem, algorithm="RS256", headers={"kid": identity.kid})


def sign_delegation_jwt(
    *,
    audience: str,
    user_sub: str,
    additional_claims: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = DEFAULT_DELEGATION_TTL_SECONDS,
) -> str:
    """Sign an RFC 8693 delegation JWT.

    Used by Mantle when proxying a user request to Chorus: the JWT identifies the
    user (`sub = user_sub`) but records that Mantle is the actor performing the
    delegation (`act.sub = "mantle"`).

    Chorus persona handlers verify both `aud` (matches their persona client_id)
    and `act.sub` (the issuer's name) before accepting the delegation.
    """
    identity = get_service_identity()
    now = int(time.time())
    claims: Dict[str, Any] = {
        "iss": identity.name,
        "sub": user_sub,
        "aud": audience,
        "act": {"sub": identity.name},
        "principal_type": "delegation",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    if additional_claims:
        for k, v in additional_claims.items():
            claims.setdefault(k, v)

    pem = identity.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return jose_jwt.encode(claims, pem, algorithm="RS256", headers={"kid": identity.kid})
