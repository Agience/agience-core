"""Origin auth issuance + low-level helpers.

Owns:
- JWT issuance (user, server, delegation tokens)
- Refresh token + nonce issuance
- Password hashing (PBKDF2)
- API key generation + hashing
- Allow-list and redirect-uri checks
- PKCE helpers
- OAuth2 error constants

Verification (`verify_token`, `verify_api_key`, `verify_nonce`) lives in
`origin/services/auth_verifier.py`. Origin signs; both Origin and Mantle verify.
"""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import urlparse

from jose import jwt

from kernel import config
from kernel.key_manager import get_key_id, get_private_key_pem

JWT_ALGORITHM = "RS256"
ACCESS_TOKEN_EXPIRE_HOURS = 12
NONCE_TTL_SECONDS = 1800

# Password hashing
_PWD_ALG = "pbkdf2_sha256"


# ---------------------------------------------------------------------------
# JWT issuance
# ---------------------------------------------------------------------------
def create_jwt_token(user_data: dict, expires_hours: int = ACCESS_TOKEN_EXPIRE_HOURS) -> str:
    """Sign a JWT with Origin's RSA private key (RS256)."""
    payload = user_data.copy()
    now = datetime.now(timezone.utc)
    payload.setdefault("iat", now.timestamp())
    payload.setdefault("exp", (now + timedelta(hours=expires_hours)).timestamp())
    payload.setdefault("iss", config.AUTHORITY_ISSUER)
    return jwt.encode(
        payload,
        get_private_key_pem(),
        algorithm=JWT_ALGORITHM,
        headers={"kid": get_key_id()},
    )


def issue_delegation_token(server_client_id: str, user_id: str, ttl_seconds: int = 300) -> str:
    """Short-lived RFC 8693 delegation JWT — server acting on behalf of a user.

    sub=user_id, aud=server_client_id, act.sub=server_client_id,
    principal_type=delegation. The host_id is best-effort: if the platform
    topology hasn't been seeded (Origin doesn't own it), it ships empty.
    """
    host_id = ""
    try:
        from services.platform_topology import get_id_optional
        from services.bootstrap_types import HOST_ARTIFACT_SLUG

        host_id = get_id_optional(HOST_ARTIFACT_SLUG) or ""
    except Exception:
        host_id = ""

    now = datetime.now(timezone.utc)
    payload = {
        "iss": config.AUTHORITY_ISSUER,
        "sub": user_id,
        "aud": server_client_id,
        "act": {"sub": server_client_id},
        "principal_type": "delegation",
        "host_id": host_id,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=ttl_seconds)).timestamp(),
    }
    return jwt.encode(
        payload,
        get_private_key_pem(),
        algorithm=JWT_ALGORITHM,
        headers={"kid": get_key_id()},
    )


# ---------------------------------------------------------------------------
# Password (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------
def _pbkdf2_sha256(password: str, salt: bytes, iters: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)


def hash_password(password: str) -> str:
    """Hash a password. Stored format: pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>."""
    if not isinstance(password, str) or not password:
        raise ValueError("Password is required")
    iters = int(getattr(config, "PASSWORD_PBKDF2_ITERS", 0) or 200_000)
    salt = secrets.token_bytes(16)
    dk = _pbkdf2_sha256(password, salt, iters)
    return f"{_PWD_ALG}${iters}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not password or not stored_hash:
        return False
    try:
        alg, iters_s, salt_b64, dk_b64 = stored_hash.split("$", 3)
        if alg != _PWD_ALG:
            return False
        salt = _b64d(salt_b64)
        expected = _b64d(dk_b64)
        actual = _pbkdf2_sha256(password, salt, int(iters_s))
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def dummy_verify_password(password: str) -> None:
    """Spend roughly the same CPU as a real verify — anti-enumeration."""
    try:
        iters = int(getattr(config, "PASSWORD_PBKDF2_ITERS", 0) or 200_000)
        secrets.compare_digest(_pbkdf2_sha256(password or "", b"\x00" * 16, iters), b"\x00" * 32)
    except Exception:
        return


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4))


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
def generate_api_key() -> str:
    """Generate a new raw API key (`agc_<32 hex>`)."""
    return f"agc_{secrets.token_bytes(16).hex()}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Nonce — stateless HMAC challenge tokens
# ---------------------------------------------------------------------------
def issue_nonce(key_id: str, artifact_id: str, secret: str) -> Tuple[str, datetime]:
    if not secret:
        raise ValueError("INBOUND_NONCE_SECRET is not configured")
    ts = str(int(time.time()))
    payload = f"{ts}:{artifact_id}:{key_id}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}:{sig}".encode("utf-8")).decode("utf-8")
    return token, datetime.fromtimestamp(int(ts) + NONCE_TTL_SECONDS, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Allow-list + redirect-uri checks
# ---------------------------------------------------------------------------
def _match_exact_or_glob(value: str, exact: set[str], patterns: list[str]) -> bool:
    if value in exact:
        return True
    return any(fnmatch.fnmatchcase(value, p) for p in patterns)


def is_person_allowed(google_id: Optional[str], email: Optional[str]) -> bool:
    """Allow-list gate. Default-allow when nothing is configured.

    Reads from `core.config` at call time so DB-loaded settings (Phase 2) win.
    """
    allowed_emails = getattr(config, "ALLOWED_EMAILS", None) or []
    allowed_domains = getattr(config, "ALLOWED_DOMAINS", None) or []
    allowed_google_ids = getattr(config, "ALLOWED_GOOGLE_IDS", None) or []

    if not (allowed_emails or allowed_domains or allowed_google_ids):
        return True
    if "*" in allowed_emails or "*" in allowed_domains or "*" in allowed_google_ids:
        return True

    gid_ok = bool(google_id) and google_id in set(allowed_google_ids)

    email_l = (email or "").lower()
    domain = email_l.split("@")[-1] if "@" in email_l else ""

    exact_emails = {e.lower() for e in allowed_emails if "*" not in e}
    email_patterns = [e.lower() for e in allowed_emails if "*" in e]
    exact_domains = {d.lower() for d in allowed_domains if "*" not in d}
    domain_patterns = [d.lower() for d in allowed_domains if "*" in d]

    email_ok = bool(email_l) and _match_exact_or_glob(email_l, exact_emails, email_patterns)
    domain_ok = bool(domain) and _match_exact_or_glob(domain, exact_domains, domain_patterns)
    return gid_ok or email_ok or domain_ok


def is_client_redirect_allowed(uri: str) -> bool:
    """Built-in platform client redirect-uri check (RFC 8252 + well-known tools)."""
    allowed_bases = [config.FACET_URI, getattr(config, "ORIGIN_URI", "")]
    always_allowed = {"https://vscode.dev", "https://oauth.pstmn.io"}
    allowed_loopback_hosts = {"127.0.0.1", "localhost"}

    backend_local = (getattr(config, "ORIGIN_URI", "") or "").startswith(("http://localhost", "http://127.0.0.1"))
    frontend_local = (config.FACET_URI or "").startswith(("http://localhost", "http://127.0.0.1"))
    if backend_local or frontend_local:
        allowed_bases.extend([f"http://localhost:{p}" for p in range(3000, 9000)])

    try:
        parsed = urlparse(uri)
        if parsed.scheme not in ("http", "https"):
            return False
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        if base_url in allowed_bases or base_url in always_allowed:
            return True
        if parsed.scheme == "http" and parsed.hostname in allowed_loopback_hosts:
            return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------
def generate_pkce_challenge() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return code_verifier, code_challenge


def verify_pkce_challenge(code_verifier: str, code_challenge: str, method: str = "S256") -> bool:
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    elif method == "plain":
        computed = code_verifier
    else:
        return False
    return secrets.compare_digest(computed, code_challenge)


# ---------------------------------------------------------------------------
# OAuth2 error constants
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
