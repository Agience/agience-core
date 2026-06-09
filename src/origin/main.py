"""Origin — FastAPI app entry point.

Listens on port 8080. Responsible for identity, OIDC, grants, passkeys, OTP,
API keys, server credentials, platform settings, setup, and gate.

In substep 1.1a-ii: auth_router is wired. passkey/otp/setup move in 1.1b/1.1e.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from kernel import config
from kernel.key_manager import (
    get_jwk_public,
    get_key_id,
    init_encryption_key,
    init_jwt_keys,
    init_nonce_secret,
    init_setup_token,
)
from origin.db.session import SessionLocal, build_database_url, init_engine
from origin.routers.api_keys_router import internal_router as api_keys_internal_router
from origin.routers.api_keys_router import router as api_keys_router
from origin.routers.auth_router import auth_router as auth_router_module
from origin.routers.auth_router import internal_router as auth_internal_router
from origin.routers.auth_router import root_router as auth_root_router
from origin.routers.grants_router import internal_router as grants_internal_router
from origin.routers.grants_router import router as grants_router
from origin.routers.otp_router import otp_router
from origin.routers.passkey_router import passkey_router
from origin.routers.platform_router import platform_router
from origin.routers.server_credentials_router import router as server_credentials_router
from origin.routers.setup_router import setup_router
from origin.services import manifest as manifest_loader
from origin.services.oidc_providers import reload_oauth_providers
from origin.services.platform_settings_service import settings as platform_settings

logger = logging.getLogger("agience.origin")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03dZ %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


# ---------------------------------------------------------------------------
# Build info
# ---------------------------------------------------------------------------
BUILD_INFO_PATH = os.getenv("BUILD_INFO_PATH", "/app/build_info.json")


def _load_build_info() -> dict:
    for candidate in [BUILD_INFO_PATH, str(Path(__file__).resolve().parent.parent / "build_info.json")]:
        try:
            data = json.loads(Path(candidate).read_text(encoding="utf-8"))
            # `build_time` is stamped by `.scripts/stamp_build_time.py` at image
            # build time; ensure the key is always present so the /version
            # contract is stable in dev.
            data.setdefault("build_time", "")
            return data
        except (OSError, json.JSONDecodeError):
            continue
    return {"version": "", "build_time": ""}


BUILD_INFO = _load_build_info()


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
def _run_migrations() -> None:
    here = Path(__file__).resolve().parent
    cfg = AlembicConfig(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "alembic"))
    cfg.set_main_option("sqlalchemy.url", build_database_url())
    logger.info("Origin: running alembic upgrade to head")
    command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Config rebinding from platform_settings (SQLite-backed)
# ---------------------------------------------------------------------------
def _apply_db_settings_to_config() -> None:
    """Read platform_settings from the DB and rebind kernel.config attributes.

    Mirrors what Mantle's `config.load_settings_from_db()` does, but from
    Origin's SQLite-backed cache. Only the subset of settings Origin
    consumes is rebound here. Skipped keys keep their Phase-1 defaults.
    """
    # OAuth providers — secrets come from `secret_value`, plain values from `value`.
    config.GOOGLE_OAUTH_CLIENT_ID = platform_settings.get("auth.google.client_id")
    config.GOOGLE_OAUTH_CLIENT_SECRET = platform_settings.get_secret("auth.google.client_secret")
    config.GOOGLE_OAUTH_REDIRECT_URI = platform_settings.get("auth.google.redirect_uri")

    config.MICROSOFT_ENTRA_TENANT = platform_settings.get("auth.microsoft.tenant", "common")
    config.MICROSOFT_ENTRA_CLIENT_ID = platform_settings.get("auth.microsoft.client_id")
    config.MICROSOFT_ENTRA_CLIENT_SECRET = platform_settings.get_secret("auth.microsoft.client_secret")
    config.MICROSOFT_ENTRA_REDIRECT_URI = platform_settings.get("auth.microsoft.redirect_uri")

    config.AUTH0_DOMAIN = platform_settings.get("auth.auth0.domain")
    config.AUTH0_CLIENT_ID = platform_settings.get("auth.auth0.client_id")
    config.AUTH0_CLIENT_SECRET = platform_settings.get_secret("auth.auth0.client_secret")
    config.AUTH0_REDIRECT_URI = platform_settings.get("auth.auth0.redirect_uri")

    config.CUSTOM_OIDC_NAME = platform_settings.get("auth.custom.name")
    config.CUSTOM_OIDC_METADATA_URL = platform_settings.get("auth.custom.metadata_url")
    config.CUSTOM_OIDC_CLIENT_ID = platform_settings.get("auth.custom.client_id")
    config.CUSTOM_OIDC_CLIENT_SECRET = platform_settings.get_secret("auth.custom.client_secret")
    config.CUSTOM_OIDC_REDIRECT_URI = platform_settings.get("auth.custom.redirect_uri")
    config.CUSTOM_OIDC_SCOPES = platform_settings.get("auth.custom.scopes") or "openid email profile"

    # Branding / URIs — Origin signs JWTs with `iss = AUTHORITY_ISSUER`. Default
    # to `ORIGIN_URI` env so dev works without DB settings.
    fe = platform_settings.get("branding.facet_uri")
    if fe:
        config.FACET_URI = fe
    config.AUTHORITY_ISSUER = (
        os.getenv("ORIGIN_URI") or fe or getattr(config, "AUTHORITY_ISSUER", "http://localhost:8080")
    )

    # Allow lists (used by `is_person_allowed`).
    raw = platform_settings.get("auth.allowed_emails", "")
    config.ALLOWED_EMAILS = [e.strip() for e in (raw or "").split(",") if e.strip()]
    raw = platform_settings.get("auth.allowed_domains", "")
    config.ALLOWED_DOMAINS = [d.strip() for d in (raw or "").split(",") if d.strip()]
    raw = platform_settings.get("auth.allowed_google_ids", "")
    config.ALLOWED_GOOGLE_IDS = [g.strip() for g in (raw or "").split(",") if g.strip()]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 0 — key material from disk (must exist; init container writes them)
    # kid="origin-1" matches the kid published in the authority manifest
    # (init container writes origin's JWKS with that kid) and the service_identity kid.
    init_jwt_keys(key_id="origin-1")
    init_encryption_key()
    init_nonce_secret()
    init_setup_token()
    # Origin's service identity (origin.private.pem) — same key used for both
    # service-to-service mutual JWTs AND user tokens (the OIDC issuer signing key).
    from kernel import service_identity
    service_identity.init_service_identity("origin")

    # Phase 1.5 — DB engine + alembic
    init_engine()
    if os.getenv("ORIGIN_SKIP_MIGRATIONS") != "1":
        _run_migrations()

    # Phase 2 — load settings, apply manifest if present, rebind config, register providers
    if os.getenv("ORIGIN_SKIP_DB_SETTINGS") != "1":
        with SessionLocal() as session:
            platform_settings.load_all(session)
            manifest_doc = manifest_loader.load()
            if manifest_doc:
                manifest_loader.apply(session, manifest_doc)
                session.commit()
                # Re-load cache so downstream code sees manifest-applied values.
                platform_settings.load_all(session)
        _apply_db_settings_to_config()
    reload_oauth_providers()

    logger.info("Origin: ready (kid=%s, providers=%d)", get_key_id(), len(_registered_providers()))
    yield


def _registered_providers() -> dict:
    from origin.services.oidc_providers import REGISTERED_PROVIDERS

    return REGISTERED_PROVIDERS


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Agience Origin",
    description="Identity, OIDC, grants, passkeys, OTP, API keys, server credentials.",
    version=BUILD_INFO.get("version") or "0.0.0-dev",
    lifespan=lifespan,
)


def _allowed_origins() -> list[str]:
    raw = os.getenv("ORIGIN_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    # Bearer-only XHR is safe with allow_origins=["*"]; OAuth redirect cookies
    # are same-site (browser nav, not XHR) so CORS doesn't apply.
    return ["*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_session_secret() -> str:
    """Same pattern as Mantle's main.py — read platform_internal.secret directly."""
    from kernel.config import KEYS_DIR
    secret_path = KEYS_DIR / "platform_internal.secret"
    if secret_path.exists():
        try:
            return secret_path.read_text().strip()
        except OSError:
            pass
    return "bootstrap-session-key-replace-after-first-boot"


app.add_middleware(
    SessionMiddleware,
    secret_key=_read_session_secret(),
    max_age=12 * 60 * 60,
)


# ---------------------------------------------------------------------------
# Global exception handler — keep tracebacks out of HTTP responses.
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_logger(request: Request, exc: Exception):
    logger.exception(
        "HTTP 500 %s %s error=%s",
        request.method,
        request.url.path,
        repr(exc),
    )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router_module)
app.include_router(auth_root_router)
app.include_router(auth_internal_router)
app.include_router(passkey_router)
app.include_router(otp_router)
app.include_router(api_keys_router)
app.include_router(api_keys_internal_router)
app.include_router(server_credentials_router)
# Internal router registers FIRST so its specific paths (/check,
# /lookup-by-key, /by-principal-resource, /by-grantee, /upsert) match
# before the generic /{grant_id} route eats them.
app.include_router(grants_internal_router)
app.include_router(grants_router)
app.include_router(setup_router)
app.include_router(platform_router)


# ---------------------------------------------------------------------------
# Health / version
# ---------------------------------------------------------------------------
@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/version", tags=["health"])
def version() -> dict:
    return BUILD_INFO


# JWKS is also served by `auth_router.root_router` at /.well-known/jwks.json.
# Keep this minimal duplicate so older callers checking the bare path keep working
# during the rollout — it returns the same data.
@app.get("/.well-known/jwks.json", include_in_schema=False)
def jwks_root() -> dict:
    return {"keys": [get_jwk_public()]}
