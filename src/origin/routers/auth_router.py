"""Origin's auth router — OAuth, password, refresh, client_credentials, /me, /nonce.

Cross-DB MCP client lookup is delegated to Mantle via `clients.mantle_client.MantleClient`.

Out of scope here (intentionally NOT ported):
- `/auth/passkey/*` — moves with `passkey_router` in 1.1b
- `/auth/otp/*` — moves with `otp_router` in 1.1b
- `/auth/authorizer/complete-oauth` — relocates to a Mantle-side router
  alongside the artifact services it orchestrates (Seraph invocation,
  workspace_service). Filed as a follow-up.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import bcrypt
from authlib.common.security import generate_token
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from kernel import config
from origin.clients.mantle_client import get_mantle_client
from origin.db import server_credentials as db_server_credentials
from origin.db.session import get_db
from origin.models.person import Person as PersonModel
from origin.services import person_service
from origin.services import auth_service as origin_auth_service
from origin.services.auth_service import (
    create_jwt_token,
    dummy_verify_password,
    hash_password,
    is_client_redirect_allowed,
    issue_nonce,
    verify_password,
)
from origin.services.auth_verifier import verify_token
from origin.services.dependencies import AuthContext, get_auth, get_person
from origin.services.oidc_providers import REGISTERED_PROVIDERS, oauth
from origin.services.platform_settings_service import settings as platform_settings

logger = logging.getLogger(__name__)
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
root_router = APIRouter(tags=["Authentication"])
internal_router = APIRouter(prefix="/internal", tags=["Internal"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Internal endpoints (kernel-server auth — used by Mantle/Chorus for cross-DB lookups)
# ---------------------------------------------------------------------------
def _require_kernel_server(auth: AuthContext) -> None:
    """Phase C kernel-caller check.

    Kernel callers (Mantle, Chorus) authenticate to Origin with mutual JWTs
    signed by their own service identity, with `principal_type=service` and
    `iss` ∈ {"mantle", "chorus"}. The auth dependency `get_auth` verifies the
    JWT against the inline JWKS in the platform authority manifest before this
    function runs.
    """
    if auth.principal_type != "service":
        raise HTTPException(status_code=403, detail="Kernel service token required")
    if auth.principal_id not in {"mantle", "chorus"}:
        raise HTTPException(status_code=403, detail="Caller is not a recognized kernel service")


@internal_router.get("/persons/{person_id}")
def internal_get_person(
    person_id: str,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    """Server-to-server person lookup. Used by Mantle's `services.person_service`
    HTTP shim during the post-auth-move transition window.
    """
    _require_kernel_server(auth)
    person = person_service.get_user_by_id(db, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return _person_to_dict(person)


class _DelegationTokenRequest(BaseModel):
    """Body for POST /internal/delegation-token."""
    model_config = ConfigDict(extra="forbid")
    server_client_id: str
    user_id: str
    ttl_seconds: int = 300


@internal_router.post("/delegation-token")
def internal_issue_delegation_token(
    body: _DelegationTokenRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Mint a short-lived RFC 8693 delegation JWT.

    Mantle calls this when proxying user requests to a first-party MCP persona
    (sub=user_id, aud=server_client_id, act.sub=server_client_id,
    principal_type=delegation, exp=300s). Origin owns RSA signing keys so
    Mantle can't issue these directly; it delegates here.
    """
    _require_kernel_server(auth)
    token = origin_auth_service.issue_delegation_token(
        body.server_client_id, body.user_id, body.ttl_seconds
    )
    return {"token": token}


@internal_router.get("/operator-id")
def internal_get_operator_id(
    auth: AuthContext = Depends(get_auth),
):
    """Return the platform operator UUID from Origin's settings.

    Mantle calls this when its own ArangoDB platform_settings do not contain
    ``platform.operator_id`` (e.g. after a factory reset that wiped ArangoDB
    but left Origin's SQLite intact, or during first-login provisioning before
    the operator bootstrap ran).
    """
    _require_kernel_server(auth)
    return {"operator_id": platform_settings.get("platform.operator_id") or ""}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str
    password: str


class PasswordRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str
    name: str = ""
    email: str = ""


class LinkProviderRequest(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_email(user_info: dict) -> str:
    email = (
        (user_info.get("email") or "").strip()
        or (user_info.get("preferred_username") or "").strip()
        or (user_info.get("upn") or "").strip()
    )
    if not email:
        emails = user_info.get("emails")
        if isinstance(emails, list) and emails:
            email = str(emails[0]).strip()
    return email


def _extract_name(user_info: dict) -> str:
    name = (user_info.get("name") or "").strip()
    if name:
        return name
    given = (user_info.get("given_name") or "").strip()
    family = (user_info.get("family_name") or "").strip()
    if given or family:
        return (given + " " + family).strip()
    return (user_info.get("preferred_username") or "").strip() or "User"


def _person_to_dict(person: PersonModel) -> dict:
    """Serialize a Postgres Person row to the same shape Mantle emits."""
    return {
        "id": str(person.id),
        "google_id": person.google_id or "",
        "oidc_provider": person.oidc_provider or "",
        "oidc_subject": person.oidc_subject or "",
        "email": person.email or "",
        "name": person.name or "",
        "username": person.username or "",
        "picture": person.picture,
        "preferences": person.preferences or {},
        "has_password": bool(person.password_hash),
        "created_time": person.created_time.isoformat() if person.created_time else None,
        "modified_time": person.modified_time.isoformat() if person.modified_time else None,
    }


def _compute_roles(user_id: str) -> list[str]:
    """Roles for inclusion in JWTs.

    1.1a-ii scope: bootstrap operator only. Postgres-grant-based admin lookup
    lands in 1.1d when `grants_router` moves and Origin's grants table fills.
    """
    operator_id = platform_settings.get("platform.operator_id")
    if operator_id and user_id == operator_id:
        return ["platform:admin"]
    return []


# In-memory PKCE / authorization-code storage (per-process; use Redis in
# multi-replica deploys). Same pattern as Mantle's auth_router.
authorization_codes: dict[str, dict] = {}
pkce_challenges: dict[str, dict] = {}

_AUTH_CACHE_TTL = timedelta(minutes=10)
_AUTH_CACHE_MAX_ITEMS = 5000


def _prune_auth_cache(now: datetime) -> None:
    cutoff = now - _AUTH_CACHE_TTL
    for cache in (pkce_challenges, authorization_codes):
        expired = [
            k
            for k, v in cache.items()
            if isinstance(v, dict) and v.get("timestamp") and v["timestamp"] < cutoff
        ]
        for k in expired:
            cache.pop(k, None)
        while len(cache) > _AUTH_CACHE_MAX_ITEMS:
            try:
                oldest = next(iter(cache))
            except StopIteration:
                break
            cache.pop(oldest, None)


# ---------------------------------------------------------------------------
# OAuth /authorize
# ---------------------------------------------------------------------------
@auth_router.get("/authorize", dependencies=None)
async def authorize(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    provider: str = "google",
    scope: Optional[str] = None,
    state: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: Optional[str] = "S256",
    setup_operator_token: Optional[str] = None,
):
    """OAuth2 authorization endpoint. Redirects to the upstream OIDC provider.

    Validates `client_id` + `redirect_uri`. Built-in platform clients are
    validated against config; third-party MCP clients are looked up in Mantle
    via `MantleClient.find_mcp_client`.
    """
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Unsupported response_type. Only 'code' is supported.")

    mantle_lookup = get_mantle_client().find_mcp_client(client_id)
    if mantle_lookup is None:
        # Built-in platform client (or unregistered third-party): use static rules
        if not is_client_redirect_allowed(redirect_uri):
            raise HTTPException(status_code=403, detail="Invalid redirect_uri")
    else:
        if redirect_uri not in (mantle_lookup.get("redirect_uris") or []):
            raise HTTPException(status_code=400, detail="redirect_uri not registered for this client")

    if code_challenge:
        if code_challenge_method not in ("S256", "plain"):
            raise HTTPException(status_code=400, detail="Unsupported code_challenge_method.")
        if len(code_challenge) < 43 or len(code_challenge) > 128:
            raise HTTPException(
                status_code=400, detail="code_challenge must be between 43 and 128 characters"
            )

    if provider not in REGISTERED_PROVIDERS:
        raise HTTPException(
            status_code=400, detail=f"Unknown or unconfigured provider: {provider}"
        )

    _prune_auth_cache(datetime.now(timezone.utc))
    oauth_state = generate_token(32)
    auth_request = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "provider": provider,
        "scope": scope or "read",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "expected_iss": REGISTERED_PROVIDERS[provider].get("issuer"),
        "timestamp": datetime.now(timezone.utc),
    }
    if setup_operator_token:
        auth_request["setup_operator_token"] = setup_operator_token
    pkce_challenges[oauth_state] = auth_request

    oauth_client = oauth.create_client(provider)
    if not oauth_client:
        raise HTTPException(status_code=500, detail=f"Provider not available: {provider}")

    extra_kwargs: dict = {}
    try:
        server_metadata = await oauth_client.load_server_metadata()
        if "offline_access" in (server_metadata.get("scopes_supported") or []):
            extra_kwargs["scope"] = (
                REGISTERED_PROVIDERS[provider].get("scope", "openid email profile") + " offline_access"
            )
    except Exception:
        pass

    return await oauth_client.authorize_redirect(
        request,
        redirect_uri=REGISTERED_PROVIDERS[provider]["redirect_uri"],
        state=oauth_state,
        **extra_kwargs,
    )


# ---------------------------------------------------------------------------
# OAuth /callback
# ---------------------------------------------------------------------------
@auth_router.get("/callback")
async def auth_callback(request: Request):
    try:
        oauth_state = request.query_params.get("state")
        if not oauth_state or oauth_state not in pkce_challenges:
            raise HTTPException(status_code=400, detail="Invalid or expired state parameter")
        auth_request = pkce_challenges[oauth_state]
        provider = auth_request.get("provider") or "google"

        callback_iss = request.query_params.get("iss")
        expected_iss = auth_request.get("expected_iss")
        if expected_iss and callback_iss and callback_iss != expected_iss:
            logger.warning(
                "RFC 9207 iss mismatch for %s: expected %r got %r", provider, expected_iss, callback_iss
            )
            raise HTTPException(status_code=400, detail="Authorization server mismatch (iss parameter)")

        oauth_client = oauth.create_client(provider)
        if not oauth_client:
            raise HTTPException(status_code=500, detail=f"Provider not available: {provider}")

        token = await oauth_client.authorize_access_token(request)
        user_info = token.get("userinfo")
        if not user_info:
            try:
                user_info = await oauth_client.userinfo(token=token)
            except Exception:
                user_info = None
        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to fetch user info")

        email = _extract_email(user_info)
        name = _extract_name(user_info)
        if not email:
            raise HTTPException(status_code=400, detail="Provider did not return an email address")

        google_id = user_info.get("sub") if provider == "google" else None
        from origin.services.auth_service import is_person_allowed

        if not is_person_allowed(google_id, email):
            error_params = {"error": "access_denied", "error_description": "User not allowed"}
            if auth_request.get("state"):
                error_params["state"] = auth_request["state"]
            return RedirectResponse(
                url=f"{auth_request['redirect_uri']}?{urlencode(error_params)}",
                status_code=status.HTTP_302_FOUND,
            )

        _prune_auth_cache(datetime.now(timezone.utc))
        auth_code = generate_token(32)
        authorization_codes[auth_code] = {
            "user_info": {
                "provider": provider,
                "sub": user_info["sub"],
                "email": email.lower(),
                "name": name,
                "picture": user_info.get("picture"),
            },
            "client_id": auth_request["client_id"],
            "redirect_uri": auth_request["redirect_uri"],
            "scope": auth_request["scope"],
            "code_challenge": auth_request.get("code_challenge"),
            "code_challenge_method": auth_request.get("code_challenge_method"),
            "timestamp": datetime.now(timezone.utc),
        }
        if auth_request.get("setup_operator_token"):
            authorization_codes[auth_code]["setup_operator_token"] = auth_request["setup_operator_token"]
        _prune_auth_cache(datetime.now(timezone.utc))

        params = {"code": auth_code}
        if auth_request["state"]:
            params["state"] = auth_request["state"]
        return RedirectResponse(
            url=f"{auth_request['redirect_uri']}?{urlencode(params)}",
            status_code=status.HTTP_302_FOUND,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Authentication error: %s", exc)
        oauth_state = request.query_params.get("state")
        if oauth_state and oauth_state in pkce_challenges:
            auth_request = pkce_challenges[oauth_state]
            error_params = {"error": "server_error", "error_description": "Authentication failed"}
            if auth_request["state"]:
                error_params["state"] = auth_request["state"]
            return RedirectResponse(
                url=f"{auth_request['redirect_uri']}?{urlencode(error_params)}",
                status_code=status.HTTP_302_FOUND,
            )
        return JSONResponse(
            status_code=400,
            content={"error": "server_error", "error_description": "Authentication failed"},
        )


# ---------------------------------------------------------------------------
# OAuth /token
# ---------------------------------------------------------------------------
@auth_router.post("/token")
async def token_endpoint(
    background_tasks: BackgroundTasks,
    grant_type: str = Form(...),
    code: Optional[str] = Form(None),
    redirect_uri: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    client_secret: Optional[str] = Form(None),
    code_verifier: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if grant_type == "authorization_code":
        if not all([code, redirect_uri, client_id, code_verifier]):
            raise HTTPException(
                status_code=400,
                detail="Missing one or more required parameters: code, redirect_uri, client_id, code_verifier",
            )
        return await _grant_authorization_code(
            db=db,
            background_tasks=background_tasks,
            code=code,           # type: ignore[arg-type]
            redirect_uri=redirect_uri,  # type: ignore[arg-type]
            client_id=client_id,        # type: ignore[arg-type]
            code_verifier=code_verifier,
        )
    if grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Missing required parameter: refresh_token")
        return await _grant_refresh_token(background_tasks=background_tasks, refresh_token=refresh_token)
    if grant_type == "client_credentials":
        if not client_id or not client_secret:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_request", "error_description": "client_id and client_secret are required"},
            )
        return await _grant_client_credentials(db=db, client_id=client_id, client_secret=client_secret)

    raise HTTPException(
        status_code=400,
        detail="Unsupported grant_type. Only 'authorization_code', 'refresh_token', and 'client_credentials' are supported.",
    )


async def _grant_authorization_code(
    *,
    db: Session,
    background_tasks: BackgroundTasks,
    code: str,
    redirect_uri: str,
    client_id: str,
    code_verifier: Optional[str],
):
    if code not in authorization_codes:
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")
    auth_data = authorization_codes[code]
    _prune_auth_cache(datetime.now(timezone.utc))

    if client_id != auth_data["client_id"]:
        raise HTTPException(status_code=400, detail="Invalid client_id")
    if redirect_uri != auth_data["redirect_uri"]:
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")
    if datetime.now(timezone.utc) - auth_data["timestamp"] > _AUTH_CACHE_TTL:
        del authorization_codes[code]
        raise HTTPException(status_code=400, detail="Authorization code expired")

    if auth_data.get("code_challenge"):
        if not code_verifier:
            raise HTTPException(status_code=400, detail="Missing code_verifier for PKCE")
        if auth_data["code_challenge_method"] == "S256":
            digest = hashlib.sha256(code_verifier.encode()).digest()
            verifier_challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        else:
            verifier_challenge = code_verifier
        if not secrets.compare_digest(verifier_challenge, auth_data["code_challenge"]):
            raise HTTPException(status_code=400, detail="Invalid code_verifier")

    del authorization_codes[code]

    info = auth_data["user_info"]
    try:
        user = person_service.get_or_create_user_by_oidc_identity(
            db,
            oidc_provider=info.get("provider") or "google",
            oidc_subject=info["sub"],
            email=info.get("email", ""),
            name=info.get("name", ""),
            picture=info.get("picture"),
        )
        db.commit()
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc))

    if not user:
        raise HTTPException(status_code=500, detail="Failed to create or retrieve user")
    logger.info("User authenticated: %s (%s)", user.email, user.id)

    # Setup-operator one-shot promotion: when the wizard hands off via OAuth.
    setup_op_token = auth_data.get("setup_operator_token")
    if setup_op_token:
        stored = platform_settings.get("platform.setup_operator_token")
        if (
            stored
            and not platform_settings.get("platform.operator_id")
            and platform_settings.get("platform.setup_complete") == "true"
            and secrets.compare_digest(stored, setup_op_token)
        ):
            platform_settings.set_many(
                db,
                [
                    {"key": "platform.operator_id", "value": str(user.id), "category": "platform", "is_secret": False},
                    {"key": "platform.setup_operator_token", "value": "", "category": "platform", "is_secret": True},
                ],
                updated_by=str(user.id),
            )
            logger.info("Setup token validated: promoted %s (%s) to platform operator", user.email, user.id)

    issuing_client_id = auth_data["client_id"]
    mantle_lookup = get_mantle_client().find_mcp_client(issuing_client_id)

    if mantle_lookup is None:
        # Built-in platform client → full user JWT
        user_data = {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
            "roles": _compute_roles(str(user.id)),
            "client_id": issuing_client_id,
            "aud": config.AUTHORITY_ISSUER,
        }
    else:
        # Third-party MCP OAuth client → scoped token (no PII)
        requested_scopes = set((auth_data.get("scope") or "read").split())
        allowed_scopes = set(mantle_lookup.get("allowed_oauth_scopes") or ["read"])
        granted_scopes = sorted(requested_scopes & allowed_scopes) or ["read"]
        user_data = {
            "sub": str(user.id),
            "aud": issuing_client_id,
            "principal_type": "mcp_client",
            "scopes": granted_scopes,
        }

    access_token = create_jwt_token(user_data)
    refresh_token = create_jwt_token({**user_data, "token_type": "refresh"}, expires_hours=24 * 30)

    background_tasks.add_task(person_service.record_person_event, user_data, "auth_grant")
    return JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 3600 * 12,
            "refresh_token": refresh_token,
            "scope": auth_data["scope"],
        }
    )


async def _grant_refresh_token(*, background_tasks: BackgroundTasks, refresh_token: str):
    payload = verify_token(refresh_token)
    if not payload or payload.get("token_type") != "refresh":
        raise HTTPException(status_code=400, detail="Invalid refresh token")
    if not payload.get("aud"):
        raise HTTPException(status_code=400, detail="Refresh token has no audience — please log in again")

    user_data = {k: v for k, v in payload.items() if k not in ("exp", "token_type", "iat")}
    access_token = create_jwt_token(user_data)
    background_tasks.add_task(person_service.record_person_event, user_data, "refresh_grant")
    return JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 3600 * 12,
            "scope": " ".join(user_data.get("scopes", [])) or "read write",
        }
    )


async def _grant_client_credentials(*, db: Session, client_id: str, client_secret: str):
    """OAuth client_credentials grant — for external MCP clients only.

    Phase C: the kernel-server fast-path is **removed**. First-party persona
    servers (Chorus) and Mantle no longer ask Origin for tokens — they sign
    their own with `chorus.private.pem / mantle.private.pem`, and peers verify
    via the inline JWKS in the platform authority manifest.

    What remains is the standard OAuth path: external MCP clients register a
    client artifact via `/auth/clients` (was `/server-credentials`), receive a
    bcrypt-hashed `client_secret`, and exchange it here for a 1-hour JWT.
    """
    credential = db_server_credentials.get_by_client_id(db, client_id)
    if not credential or not credential.is_active:
        return JSONResponse(
            status_code=401,
            content={"error": "invalid_client", "error_description": "Unknown or inactive client_id"},
        )
    if not bcrypt.checkpw(client_secret.encode(), credential.secret_hash.encode()):
        return JSONResponse(
            status_code=401,
            content={"error": "invalid_client", "error_description": "Invalid client_secret"},
        )
    db_server_credentials.update_last_used(db, credential.id)
    db.commit()

    server_claims = {
        "sub": f"server/{credential.client_id}",
        "aud": "agience",
        "principal_type": "server",
        "authority": credential.authority,
        "host_id": str(credential.host_id),
        "server_id": str(credential.server_id),
        "client_id": credential.client_id,
        "scopes": list(credential.scopes or []),
        "resource_filters": dict(credential.resource_filters or {}),
    }
    return JSONResponse(
        content={
            "access_token": create_jwt_token(server_claims, expires_hours=1),
            "token_type": "bearer",
            "expires_in": 3600,
        }
    )


# ---------------------------------------------------------------------------
# /providers
# ---------------------------------------------------------------------------
@auth_router.get("/providers", dependencies=None)
async def list_providers():
    providers = sorted(
        (
            {"name": name, "label": meta.get("label", name), "type": meta.get("type", "oidc")}
            for name, meta in REGISTERED_PROVIDERS.items()
        ),
        key=lambda p: p["label"],
    )
    email_configured = False
    try:
        from origin.services.email_service import is_configured as _email_configured

        email_configured = _email_configured()
    except Exception:
        email_configured = False
    return {
        "providers": providers,
        "password": platform_settings.get_bool("auth.password.enabled", True),
        "otp": email_configured,
    }


# ---------------------------------------------------------------------------
# Password login + register
# ---------------------------------------------------------------------------
@auth_router.post("/password/login")
async def password_login(
    background_tasks: BackgroundTasks,
    payload: PasswordLoginRequest,
    db: Session = Depends(get_db),
):
    if not platform_settings.get_bool("auth.password.enabled", True):
        raise HTTPException(status_code=404, detail="Password auth is disabled")

    identifier = (payload.identifier or "").strip()
    password = payload.password or ""
    if not identifier or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    if "@" in identifier:
        user = person_service.get_user_by_email(db, identifier.lower())
    else:
        user = person_service.get_user_by_username(db, identifier)

    if not user or not user.password_hash:
        dummy_verify_password(password)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user_data = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "roles": _compute_roles(str(user.id)),
        "client_id": getattr(config, "PLATFORM_CLIENT_ID", "platform"),
        "aud": config.AUTHORITY_ISSUER,
    }
    access_token = create_jwt_token(user_data)
    refresh_token = create_jwt_token({**user_data, "token_type": "refresh"}, expires_hours=24 * 30)
    background_tasks.add_task(person_service.record_person_event, user_data, "password_login")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 3600 * 12,
        "refresh_token": refresh_token,
        "scope": "read write",
    }


@auth_router.post("/password/register")
async def password_register(
    background_tasks: BackgroundTasks,
    payload: PasswordRegisterRequest,
    db: Session = Depends(get_db),
):
    if not platform_settings.get_bool("auth.password.enabled", True):
        raise HTTPException(status_code=404, detail="Password auth is disabled")

    username = (payload.username or "").strip()
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    name = (payload.name or "").strip()

    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if email and "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    min_len = platform_settings.get_int("auth.password.min_length", 12)
    if len(password) < min_len:
        raise HTTPException(status_code=400, detail=f"Password must be at least {min_len} characters")

    try:
        user = person_service.create_user_with_password(
            db,
            username=username,
            name=name,
            password_hash=hash_password(password),
            email=email,
        )
        db.commit()
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        logger.info("Password registration failed for username=%r (%s)", username, exc)
        raise HTTPException(status_code=400, detail="Registration failed")

    user_data = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "roles": _compute_roles(str(user.id)),
        "client_id": getattr(config, "PLATFORM_CLIENT_ID", "platform"),
        "aud": config.AUTHORITY_ISSUER,
    }
    access_token = create_jwt_token(user_data)
    refresh_token = create_jwt_token({**user_data, "token_type": "refresh"}, expires_hours=24 * 30)
    background_tasks.add_task(person_service.record_person_event, user_data, "password_register")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 3600 * 12,
        "refresh_token": refresh_token,
        "scope": "read write",
    }


# ---------------------------------------------------------------------------
# /auth/bootstrap/claim — first-operator bootstrap (Phase B)
# ---------------------------------------------------------------------------

class BootstrapClaimRequest(BaseModel):
    """Body for `POST /auth/bootstrap/claim`. The token comes from init's stdout."""
    model_config = ConfigDict(extra="forbid")
    token: str
    email: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None


class BootstrapClaimResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    person_id: str


@auth_router.post("/bootstrap/claim", response_model=BootstrapClaimResponse)
async def bootstrap_claim(body: BootstrapClaimRequest, db: Session = Depends(get_db)):
    """Claim the platform's bootstrap token to create the first operator.

    On first boot the init container generates a random token, prints it to
    stdout, and stores its sha256 in the platform authority manifest. The
    operator presents the cleartext token here exactly once; in exchange they
    get a person record, a `can_admin` grant on the authority artifact, and
    an access token. After this call, `platform.setup_complete=true` blocks
    any further claim attempts.

    Single-use. Consumes the bootstrap regardless of email/password — if
    those fields are absent, the operator is created passwordless and can
    later link an OAuth provider, set a password, or register a passkey.
    """
    from kernel import authority_trust
    from origin.db import grants as db_grants

    if (platform_settings.get("platform.setup_complete") or "").lower() == "true":
        raise HTTPException(status_code=410, detail="Bootstrap already completed")

    try:
        manifest = authority_trust.get_authority_manifest()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Authority manifest not found — re-run the init container",
        )

    if not manifest.bootstrap_token_hash:
        raise HTTPException(status_code=410, detail="Bootstrap token already consumed")

    presented_hash = hashlib.sha256(body.token.strip().encode("utf-8")).hexdigest()
    if not secrets.compare_digest(presented_hash, manifest.bootstrap_token_hash):
        raise HTTPException(status_code=401, detail="Invalid bootstrap token")

    if body.password and len(body.password) < 12:
        raise HTTPException(status_code=422, detail="Password must be at least 12 characters")

    op_email = (body.email or "").strip().lower()
    person_name = (body.name or "").strip() or (op_email.split("@")[0] if op_email else "operator")
    password_hash = hash_password(body.password) if body.password else None

    person = person_service.create_user_with_password(
        db,
        username=person_name,
        name=person_name,
        password_hash=password_hash or "",
        email=op_email,
    ) if password_hash else _create_passwordless_operator(
        db, email=op_email, name=person_name
    )

    operator_uuid = person.id  # native UUID for DB writes
    operator_id = str(person.id)  # str for JWT claims and grant grantee_id

    # Issue the platform-admin grant on the authority artifact. The operator
    # grants themselves at bootstrap; future grants flow through `/auth/grants`.
    db_grants.create(
        db,
        {
            "resource_id": manifest.artifact_id,
            "grantee_type": "user",
            "grantee_id": operator_id,
            "granted_by": operator_uuid,
            "effect": "allow",
            "can_read": True,
            "can_update": True,
            "can_admin": True,
            "can_share": True,
            "state": "active",
            "name": "Platform admin (bootstrap claim)",
        },
    )

    # Mark the bootstrap as consumed in platform_settings. This is the
    # canonical "claim happened" gate — checked at the top of this handler.
    # The artifact's bootstrap_token_hash field stays as-is (it's a hash,
    # informational only after this point).
    platform_settings.set_many(
        db,
        [
            {"key": "platform.setup_complete", "value": "true",
             "category": "platform", "is_secret": False},
            {"key": "platform.operator_id", "value": operator_id,
             "category": "platform", "is_secret": False},
        ],
        updated_by=operator_uuid,
    )
    db.commit()

    user_data = {
        "sub": operator_id,
        "email": op_email,
        "name": person_name,
        "picture": "",
        "roles": ["platform:admin"],
        "client_id": getattr(config, "PLATFORM_CLIENT_ID", "platform"),
        "aud": config.AUTHORITY_ISSUER,
    }
    access_token = create_jwt_token(user_data)
    refresh_token = create_jwt_token(
        {**user_data, "token_type": "refresh"}, expires_hours=24 * 30
    )

    logger.info(
        "Bootstrap claim consumed: operator=%s (%s)", person_name, operator_id
    )
    return BootstrapClaimResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        person_id=operator_id,
    )


def _create_passwordless_operator(db: Session, *, email: str, name: str) -> PersonModel:
    """Create the first operator without a password — they'll add one later
    via OAuth link, password reset, or passkey."""
    from origin.db import persons as db_persons

    if email and person_service.get_user_by_email(db, email):
        raise HTTPException(status_code=409, detail="Operator email already registered")
    return db_persons.create(
        db,
        {
            "email": email or None,
            "name": name,
            "username": name,
            "password_hash": None,
        },
    )


# ---------------------------------------------------------------------------
# /userinfo + /me/*
# ---------------------------------------------------------------------------
@auth_router.get("/userinfo")
async def user_info_endpoint(
    auth: AuthContext = Depends(get_auth),
    person: PersonModel = Depends(get_person),
):
    data = _person_to_dict(person)
    data["roles"] = _compute_roles(str(person.id))
    data["platform_user_id"] = config.AGIENCE_PLATFORM_USER_ID
    return data


@auth_router.get("/me/preferences")
async def get_preferences(
    auth: AuthContext = Depends(get_auth),
    person: PersonModel = Depends(get_person),
):
    return person.preferences or {}


@auth_router.patch("/me/preferences")
async def update_preferences(
    preferences: dict,
    auth: AuthContext = Depends(get_auth),
    person: PersonModel = Depends(get_person),
    db: Session = Depends(get_db),
):
    updated = person_service.update_preferences(db, str(person.id), preferences)
    db.commit()
    return updated.preferences or {}


# ---------------------------------------------------------------------------
# /nonce
# ---------------------------------------------------------------------------
@auth_router.get("/nonce", dependencies=None)
async def issue_challenge_nonce(
    request: Request,
    auth: AuthContext = Depends(get_auth),
):
    if auth.principal_type != "api_key" or not auth.api_key_entity:
        raise HTTPException(status_code=403, detail="Inbound API key required")
    if not getattr(auth.api_key_entity, "requires_nonce", False):
        raise HTTPException(status_code=403, detail="Key is not configured for inbound access")

    artifact_id = auth.target_artifact_id or ""
    key_id = auth.api_key_id or ""
    if not artifact_id or not key_id:
        raise HTTPException(status_code=400, detail="Key is not artifact-scoped")

    secret = getattr(config, "INBOUND_NONCE_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Nonce service not configured")

    token, expires_at = issue_nonce(key_id=key_id, artifact_id=artifact_id, secret=secret)
    return {"nonce": token, "expires_at": expires_at.isoformat()}


# ---------------------------------------------------------------------------
# /me/link-provider
# ---------------------------------------------------------------------------
@auth_router.post("/me/link-provider")
async def link_provider(
    body: LinkProviderRequest,
    auth: AuthContext = Depends(get_auth),
    person: PersonModel = Depends(get_person),
    db: Session = Depends(get_db),
):
    if body.code not in authorization_codes:
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")
    auth_data = authorization_codes[body.code]
    if body.redirect_uri != auth_data["redirect_uri"]:
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")
    if datetime.now(timezone.utc) - auth_data["timestamp"] > _AUTH_CACHE_TTL:
        authorization_codes.pop(body.code, None)
        raise HTTPException(status_code=400, detail="Authorization code expired")

    if auth_data.get("code_challenge"):
        if not body.code_verifier:
            raise HTTPException(status_code=400, detail="Missing code_verifier")
        if auth_data["code_challenge_method"] == "S256":
            digest = hashlib.sha256(body.code_verifier.encode()).digest()
            computed = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        else:
            computed = body.code_verifier
        if not secrets.compare_digest(computed, auth_data["code_challenge"]):
            raise HTTPException(status_code=400, detail="Invalid code_verifier")

    authorization_codes.pop(body.code, None)
    info = auth_data["user_info"]
    try:
        updated = person_service.link_oidc_identity(
            db,
            user_id=str(person.id),
            oidc_provider=info.get("provider") or "google",
            oidc_subject=info["sub"],
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))

    logger.info("Linked %s identity to user %s", info.get("provider"), person.id)
    return _person_to_dict(updated)


@auth_router.delete("/me/link-provider/{provider}")
async def unlink_provider(
    provider: str,
    auth: AuthContext = Depends(get_auth),
    person: PersonModel = Depends(get_person),
    db: Session = Depends(get_db),
):
    try:
        updated = person_service.unlink_oidc_identity(db, str(person.id))
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    logger.info("Unlinked %s identity from user %s", provider, person.id)
    return _person_to_dict(updated)


# ---------------------------------------------------------------------------
# OIDC discovery (root_router — mounted at /)
# ---------------------------------------------------------------------------
@root_router.get("/.well-known/openid-configuration")
async def openid_configuration(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        content={
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/auth/authorize",
            "token_endpoint": f"{base_url}/auth/token",
            "userinfo_endpoint": f"{base_url}/auth/userinfo",
            "jwks_uri": f"{base_url}/.well-known/jwks.json",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
            "code_challenge_methods_supported": ["S256", "plain"],
            "scopes_supported": ["read", "write", "openid", "email", "profile"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }
    )
