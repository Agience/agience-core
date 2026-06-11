"""
core/config.py

Platform configuration.

All runtime settings are stored in ArangoDB (platform_settings collection) and
loaded into module-level variables at boot. Operators may override select
values via .env. Environment values serve as defaults when the corresponding
DB setting is absent.

Consumer modules access them as ``config.SOME_VALUE`` via
``from kernel import config``.

Boot phases:
  Phase 1  (import time)  — static constants, safe defaults for all variables.
  Phase 1.5               — load_bootstrap_settings(): reads key files for
                            encryption key.
  Phase 2                 — load_settings_from_db(): rebinds all module
                            variables from the PlatformSettingsService cache.

IMPORTANT: Consumer modules must use ``from kernel import config`` and access
values as ``config.X`` in function bodies — NOT ``from kernel.config import X``
(which snapshots the value at import time and misses Phase 2 rebinding).
"""

import os
import uuid as _uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse as _urlparse, urlunparse as _urlunparse

from dotenv import load_dotenv as _load_dotenv


def _origin_only(uri: str) -> str:
    """Return scheme+host+port (strip path, query, fragment)."""
    p = _urlparse(uri)
    return _urlunparse((p.scheme, p.netloc, "", "", "", ""))

# ---------------------------------------------------------------------------
#  Phase 0: Load .env into os.environ (before any os.getenv calls)
# ---------------------------------------------------------------------------

# In Docker, kernel/ is copied to /app/kernel/ so _BACKEND_ROOT = /app and
# .env lives at /app/.env. In local dev, kernel/ lives at <repo>/src/kernel/
# so _BACKEND_ROOT = <repo>/src and .env lives one level above at <repo>/.env.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE: Optional[Path] = None
for _candidate in (_BACKEND_ROOT / ".env", _BACKEND_ROOT.parent / ".env"):
    if _candidate.is_file():
        _ENV_FILE = _candidate
        break
if _ENV_FILE:
    _load_dotenv(_ENV_FILE, override=True)

# ---------------------------------------------------------------------------
#  Phase 1: Static constants (safe at import time, never change)
# ---------------------------------------------------------------------------

# Local dev: kernel/ lives inmantle/ , so the repo root is one level above.
# Docker: kernel/ lives at /app/kernel/, so /app is the base.
BASE_DIR = _BACKEND_ROOT.parent if _BACKEND_ROOT.name == "src" else _BACKEND_ROOT
KEYS_DIR = Path(os.getenv("KEYS_DIR", str(BASE_DIR / ".data" / "keys")))

# Platform identity — deterministic UUID, never changes.
AGIENCE_PLATFORM_USER_ID = str(_uuid.uuid5(_uuid.NAMESPACE_URL, "agience://platform"))


# ---------------------------------------------------------------------------
#  Phase 1: DB-backed variables — initialized to safe defaults.
#  These are rebound in Phase 2 after settings are loaded from Postgres.
# ---------------------------------------------------------------------------

# AI — provider-agnostic. Configured via setup wizard or LLM_PROVIDER/LLM_API_KEY env vars.
# LLM_PROVIDER: openai | anthropic | openrouter | relay
# LLM_API_KEY: the API key for the configured provider.
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")
# Reasoning-grade default (deeper analysis, longer outputs).
AI_DEFAULT_MODEL: str = os.getenv("AI_DEFAULT_MODEL", "claude-sonnet-4-6")
# Quick-work default (latency-sensitive, lightweight tasks).
AI_QUICK_MODEL: str = os.getenv("AI_QUICK_MODEL", "claude-haiku-4-5-20251001")

# Embeddings — provider-agnostic via HTTP. Default points at the Agience
# embeddings server. Any provider that exposes `POST /embed {input: [str]}`
# returning `{vectors: [[float]]}` is compatible.
EMBEDDINGS_PROVIDER: str = os.getenv("EMBEDDINGS_PROVIDER", "agience")
EMBEDDINGS_URI: Optional[str] = os.getenv("EMBEDDINGS_URI")
EMBEDDINGS_API_KEY: Optional[str] = os.getenv("EMBEDDINGS_API_KEY")
# Dimension of the configured embedding model. Default matches the Agience
# embeddings server's `bge-m3` deployment (1024 dims). Override per
# deployment if a different model is in use.
EMBEDDINGS_DIM: int = int(os.getenv("EMBEDDINGS_DIM", "1024"))

# ArangoDB
ARANGO_HOST: str = os.getenv("ARANGO_HOST", "127.0.0.1")
ARANGO_PORT: int = 8529
ARANGO_USERNAME: str = "root"
ARANGO_PASSWORD: str = "root"
ARANGO_DATABASE: str = "agience"

# OAuth providers (all optional, configured via settings UI)
GOOGLE_OAUTH_CLIENT_ID: Optional[str] = None
GOOGLE_OAUTH_CLIENT_SECRET: Optional[str] = None
GOOGLE_OAUTH_REDIRECT_URI: Optional[str] = None

MICROSOFT_ENTRA_TENANT: str = "common"
MICROSOFT_ENTRA_CLIENT_ID: Optional[str] = None
MICROSOFT_ENTRA_CLIENT_SECRET: Optional[str] = None
MICROSOFT_ENTRA_REDIRECT_URI: Optional[str] = None

AUTH0_DOMAIN: Optional[str] = None
AUTH0_CLIENT_ID: Optional[str] = None
AUTH0_CLIENT_SECRET: Optional[str] = None
AUTH0_REDIRECT_URI: Optional[str] = None

CUSTOM_OIDC_NAME: Optional[str] = None
CUSTOM_OIDC_METADATA_URL: Optional[str] = None
CUSTOM_OIDC_CLIENT_ID: Optional[str] = None
CUSTOM_OIDC_CLIENT_SECRET: Optional[str] = None
CUSTOM_OIDC_REDIRECT_URI: Optional[str] = None
CUSTOM_OIDC_SCOPES: str = "openid email profile"

# Password auth
PASSWORD_AUTH_ENABLED: bool = True
PASSWORD_MIN_LENGTH: int = 12
PASSWORD_PBKDF2_ITERS: int = 200000

# JWT
JWT_KEY_ID: str = "s1"

# URIs & identity — four-container split.
#   FACET_URI   — where users access the SPA (port 80 / 5173)
#   ORIGIN_URI  — identity / OIDC issuer / JWT iss (port 8080)
#   MANTLE_URI   — artifact API (port 8081)
#   CHORUS_URI  — universal MCP gateway (port 8082)
FACET_URI: str = os.getenv("FACET_URI", "http://localhost:8080")
ORIGIN_URI: str = os.getenv("ORIGIN_URI", "http://localhost:8080")
MANTLE_URI: str = os.getenv("MANTLE_URI", "http://localhost:8081")
CHORUS_URI: str = os.getenv("CHORUS_URI", "http://localhost:8082")
PLATFORM_CLIENT_ID: str = os.getenv("PLATFORM_CLIENT_ID", "agience-client")
AUTHORITY_DOMAIN: str = _urlparse(ORIGIN_URI).hostname or "localhost"
# JWT issuer/audience identity. This is the PUBLIC origin URI and MUST be the same
# across every service (origin stamps it into `iss`; mantle/chorus validate against
# it). It is decoupled from ORIGIN_URI because mantle/chorus reach origin over the
# INTERNAL url (http://origin:8080) but must still trust the PUBLIC issuer. Set
# AUTHORITY_ISSUER=https://<domain> on every service; falls back to ORIGIN_URI for
# single-host/dev where they coincide.
AUTHORITY_ISSUER: str = _origin_only(os.getenv("AUTHORITY_ISSUER") or ORIGIN_URI)

# Features
ALLOW_LOCAL_MCP_SERVERS: bool = False

# Billing enforcement (SaaS only — when False, all gate checks pass)
BILLING_ENFORCEMENT_ENABLED: bool = False

# MANTLE encrypted search — Step 2 of the four-container migration.
# OpenSearch was retired in Step 2.6.9 (2026-05-09) and the MANTLE auth /
# encryption / SSE feature flags went with it — the encrypted MANTLE +
# MANTLE-SSE pipeline is now the only search backend.

# Desktop relay
DESKTOP_RELAY_DOWNLOAD_BASE_URL: str = "https://github.com/ikailo/agience/releases/latest/download"

# Logging
BACKEND_LOG_LEVEL: str = "info"

# Event logger (optional)
EVENT_LOGGER_URI: Optional[str] = None
EVENT_LOGGER_USERNAME: Optional[str] = None
EVENT_LOGGER_PASSWORD: Optional[str] = None

# Email
PLATFORM_EMAIL_ADDRESS: str = ""

# Access control
ALLOWED_EMAILS: list[str] = []
ALLOWED_DOMAINS: list[str] = []
ALLOWED_GOOGLE_IDS: list[str] = []

# Content storage
CONTENT_URI: str = "http://localhost:9000"
CONTENT_BUCKET: str = "agience-content"
CONTENT_DOWNLOAD_URL_EXPIRY: int = 300
CONTENT_UPLOAD_URL_EXPIRY: int = 900
CONTENT_MULTIPART_PART_URL_EXPIRY: int = 300

# Search
SEARCH_REFRESH_INTERVAL: str = "750ms"
SEARCH_CHUNK_SIZE: int = 1000
SEARCH_CHUNK_OVERLAP: int = 200
SEARCH_FIELD_WEIGHTS_PRESET: str = "description-first"

# Seed collections
SEED_COLLECTION_SLUGS: list[str] = ["agience-inbox-seeds"]

# Indexing
INDEX_QUEUE_MAX_WORKERS: int = 16

# Encryption (set in Phase 1.5 from key file)
PLATFORM_ENCRYPTION_KEY: str = ""

# Licensing (managed by key_manager, no longer env-configurable)
LICENSING_PUBLIC_KEYS_PATH: str = ""
LICENSING_PRIVATE_KEY_PATH: str = ""
LICENSING_SIGNING_KEY_ID: str = ""

# Inbound nonce HMAC secret — loaded from key file in Phase 1.5.
# Generated by the init container as inbound_nonce.secret.
INBOUND_NONCE_SECRET: str = ""


# ---------------------------------------------------------------------------
#  Phase 1.5: Bootstrap settings from key files
#  Called after key_manager init, before DB connections.
# ---------------------------------------------------------------------------

def load_bootstrap_settings() -> None:
    """
    Load encryption key and infrastructure credentials from key files.
    Must be called after key_manager.init_*() functions.

    Phase C: PLATFORM_INTERNAL_SECRET is gone. Each service holds its own
    private key and verifies peers via the inline JWKS in the platform
    authority manifest (`core.authority_trust`).
    """
    global PLATFORM_ENCRYPTION_KEY
    global ARANGO_PASSWORD, INBOUND_NONCE_SECRET

    from kernel.key_manager import (
        get_encryption_key,
        get_arango_password,
        get_nonce_secret,
    )

    PLATFORM_ENCRYPTION_KEY = get_encryption_key()
    ARANGO_PASSWORD = get_arango_password()
    INBOUND_NONCE_SECRET = get_nonce_secret()


# ---------------------------------------------------------------------------
#  Phase 2: Load all settings from DB
#  Called after PlatformSettingsService.load_all() has populated the cache.
# ---------------------------------------------------------------------------

# Mapping: setting key -> (module variable name, type converter)
_SETTING_MAP: dict[str, tuple[str, type]] = {
    # AI — canonical LLM provider + key (set via setup wizard or env).
    "ai.llm_provider": ("LLM_PROVIDER", str),
    "ai.llm_api_key": ("LLM_API_KEY", str),
    "ai.default_model": ("AI_DEFAULT_MODEL", str),
    "ai.quick_model": ("AI_QUICK_MODEL", str),
    # Embeddings (provider-agnostic; default = Agience embeddings server)
    "ai.embeddings_provider": ("EMBEDDINGS_PROVIDER", str),
    "ai.embeddings_uri": ("EMBEDDINGS_URI", str),
    "ai.embeddings_api_key": ("EMBEDDINGS_API_KEY", str),
    "ai.embeddings_dim": ("EMBEDDINGS_DIM", int),

    # ArangoDB
    "db.arango.host": ("ARANGO_HOST", str),
    "db.arango.port": ("ARANGO_PORT", int),
    "db.arango.username": ("ARANGO_USERNAME", str),
    "db.arango.database": ("ARANGO_DATABASE", str),

    # Google OAuth
    "auth.google.client_id": ("GOOGLE_OAUTH_CLIENT_ID", str),
    "auth.google.client_secret": ("GOOGLE_OAUTH_CLIENT_SECRET", str),
    "auth.google.redirect_uri": ("GOOGLE_OAUTH_REDIRECT_URI", str),

    # Microsoft Entra
    "auth.microsoft.tenant": ("MICROSOFT_ENTRA_TENANT", str),
    "auth.microsoft.client_id": ("MICROSOFT_ENTRA_CLIENT_ID", str),
    "auth.microsoft.client_secret": ("MICROSOFT_ENTRA_CLIENT_SECRET", str),
    "auth.microsoft.redirect_uri": ("MICROSOFT_ENTRA_REDIRECT_URI", str),

    # Auth0
    "auth.auth0.domain": ("AUTH0_DOMAIN", str),
    "auth.auth0.client_id": ("AUTH0_CLIENT_ID", str),
    "auth.auth0.client_secret": ("AUTH0_CLIENT_SECRET", str),
    "auth.auth0.redirect_uri": ("AUTH0_REDIRECT_URI", str),

    # Custom OIDC
    "auth.oidc.name": ("CUSTOM_OIDC_NAME", str),
    "auth.oidc.metadata_url": ("CUSTOM_OIDC_METADATA_URL", str),
    "auth.oidc.client_id": ("CUSTOM_OIDC_CLIENT_ID", str),
    "auth.oidc.client_secret": ("CUSTOM_OIDC_CLIENT_SECRET", str),
    "auth.oidc.redirect_uri": ("CUSTOM_OIDC_REDIRECT_URI", str),
    "auth.oidc.scopes": ("CUSTOM_OIDC_SCOPES", str),

    # Password auth
    "auth.password.enabled": ("PASSWORD_AUTH_ENABLED", lambda v: v.lower() in ("true", "1", "yes")),
    "auth.password.min_length": ("PASSWORD_MIN_LENGTH", int),
    "auth.password.pbkdf2_iters": ("PASSWORD_PBKDF2_ITERS", int),

    # URIs & identity
    "branding.facet_uri": ("FACET_URI", str),
    "branding.origin_uri": ("ORIGIN_URI", str),
    "platform.client_id": ("PLATFORM_CLIENT_ID", str),

    # Features
    "platform.allow_local_mcp_servers": ("ALLOW_LOCAL_MCP_SERVERS", lambda v: v.lower() in ("true", "1", "yes")),

    # Desktop relay
    "platform.desktop_relay_download_base_url": ("DESKTOP_RELAY_DOWNLOAD_BASE_URL", str),

    # Logging
    "platform.log_level": ("BACKEND_LOG_LEVEL", lambda v: v.lower()),

    # Event logger
    "platform.event_logger_uri": ("EVENT_LOGGER_URI", str),
    "platform.event_logger_username": ("EVENT_LOGGER_USERNAME", str),
    "platform.event_logger_password": ("EVENT_LOGGER_PASSWORD", str),

    # Email
    "email.from_address": ("PLATFORM_EMAIL_ADDRESS", str),

    # Access control (these are CSV lists, handled specially)
    "auth.allowed_emails": ("ALLOWED_EMAILS", None),
    "auth.allowed_domains": ("ALLOWED_DOMAINS", None),
    "auth.allowed_google_ids": ("ALLOWED_GOOGLE_IDS", None),

    # Content storage
    "storage.content_uri": ("CONTENT_URI", str),
    "storage.content_bucket": ("CONTENT_BUCKET", str),
    "storage.content_download_url_expiry": ("CONTENT_DOWNLOAD_URL_EXPIRY", int),
    "storage.content_upload_url_expiry": ("CONTENT_UPLOAD_URL_EXPIRY", int),
    "storage.content_multipart_part_url_expiry": ("CONTENT_MULTIPART_PART_URL_EXPIRY", int),

    # OpenSearch retired in Step 2.6.9 (2026-05-09); search runs on
    # encrypted MANTLE+SSE blobs in S3, configured via STORAGE_* keys above.

    # Search tuning
    "search.refresh_interval": ("SEARCH_REFRESH_INTERVAL", str),
    "search.chunk_size": ("SEARCH_CHUNK_SIZE", int),
    "search.chunk_overlap": ("SEARCH_CHUNK_OVERLAP", int),
    "search.field_weights_preset": ("SEARCH_FIELD_WEIGHTS_PRESET", str),

    # Seed collections (CSV list, handled specially)
    "platform.seed_collection_slugs": ("SEED_COLLECTION_SLUGS", None),

    # Indexing
    "platform.index_queue_max_workers": ("INDEX_QUEUE_MAX_WORKERS", int),

    # Billing enforcement
    "platform.billing_enforcement_enabled": ("BILLING_ENFORCEMENT_ENABLED", lambda v: str(v).lower() in ("true", "1", "yes")),
}

# CSV list keys — need special handling
_CSV_LIST_KEYS = {"auth.allowed_emails", "auth.allowed_domains", "auth.allowed_google_ids", "platform.seed_collection_slugs"}


def _csv_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def load_settings_from_db() -> None:
    """
    Rebind all module-level variables from PlatformSettingsService cache.
    Must be called after PlatformSettingsService.load_all().
    """
    global ANTHROPIC_API_KEY, GOOGLE_API_KEY
    global OLLAMA_BASE_URL, AI_DEFAULT_PROVIDER, AI_DEFAULT_MODEL, AI_QUICK_MODEL
    global EMBEDDINGS_PROVIDER, EMBEDDINGS_URI, EMBEDDINGS_API_KEY, EMBEDDINGS_DIM
    global ARANGO_HOST, ARANGO_PORT, ARANGO_USERNAME, ARANGO_DATABASE
    global GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI
    global MICROSOFT_ENTRA_TENANT, MICROSOFT_ENTRA_CLIENT_ID, MICROSOFT_ENTRA_CLIENT_SECRET, MICROSOFT_ENTRA_REDIRECT_URI
    global AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET, AUTH0_REDIRECT_URI
    global CUSTOM_OIDC_NAME, CUSTOM_OIDC_METADATA_URL, CUSTOM_OIDC_CLIENT_ID, CUSTOM_OIDC_CLIENT_SECRET, CUSTOM_OIDC_REDIRECT_URI, CUSTOM_OIDC_SCOPES
    global PASSWORD_AUTH_ENABLED, PASSWORD_MIN_LENGTH, PASSWORD_PBKDF2_ITERS
    global FACET_URI, ORIGIN_URI, PLATFORM_CLIENT_ID
    global AUTHORITY_DOMAIN, AUTHORITY_ISSUER
    global ALLOW_LOCAL_MCP_SERVERS, DESKTOP_RELAY_DOWNLOAD_BASE_URL
    global BACKEND_LOG_LEVEL
    global EVENT_LOGGER_URI, EVENT_LOGGER_USERNAME, EVENT_LOGGER_PASSWORD
    global PLATFORM_EMAIL_ADDRESS
    global ALLOWED_EMAILS, ALLOWED_DOMAINS, ALLOWED_GOOGLE_IDS
    global CONTENT_URI, CONTENT_BUCKET
    global CONTENT_DOWNLOAD_URL_EXPIRY, CONTENT_UPLOAD_URL_EXPIRY, CONTENT_MULTIPART_PART_URL_EXPIRY
    global SEARCH_REFRESH_INTERVAL, SEARCH_CHUNK_SIZE, SEARCH_CHUNK_OVERLAP, SEARCH_FIELD_WEIGHTS_PRESET
    global SEED_COLLECTION_SLUGS, INDEX_QUEUE_MAX_WORKERS
    global BILLING_ENFORCEMENT_ENABLED

    from services.platform_settings_service import settings

    for setting_key, (var_name, converter) in _SETTING_MAP.items():
        # Environment variables override DB values (operator .env wins).
        env_val = os.getenv(var_name)
        if env_val is not None:
            continue

        value = settings.get(setting_key)
        if value is None:
            continue

        if setting_key in _CSV_LIST_KEYS:
            globals()[var_name] = _csv_list(value)
        elif converter is not None:
            try:
                globals()[var_name] = converter(value)
            except (ValueError, TypeError):
                pass  # keep default
        else:
            globals()[var_name] = value

    # Derived values
    _origin_uri = ORIGIN_URI
    try:
        _hostname = _urlparse(_origin_uri).hostname or "localhost"
    except Exception:
        _hostname = "localhost"
    AUTHORITY_DOMAIN = _hostname
    # Issuer is the PUBLIC origin URI (explicit env wins) — NOT the internal
    # ORIGIN_URI that mantle/chorus use to reach origin. ORIGIN_URI may also include
    # a path prefix (e.g. /api) which must not appear in the JWT issuer/audience.
    AUTHORITY_ISSUER = _origin_only(os.getenv("AUTHORITY_ISSUER") or _origin_uri)
