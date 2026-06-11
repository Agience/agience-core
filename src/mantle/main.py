import os
import sys

# Ensure bare imports (`mcp_server`, `routers`, `services`, ...) resolve when
# launched as `python -m mantle.main` from the repo root. The repo root is
# already on sys.path via -m semantics; this adds the mantle/ directory itself.
_MANTLE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MANTLE_DIR not in sys.path:
    sys.path.insert(0, _MANTLE_DIR)

# E402: the sys.path bootstrap above must run before these package imports.
from datetime import datetime, timezone  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from schemas.arango.loader import init_arango_db, check_arango_health  # noqa: E402
from search.init_search import init_search, reindex_in_background, shutdown_search  # noqa: E402
from search.ingest.index_queue import start_worker as start_index_worker, stop_worker as stop_index_worker  # noqa: E402
from routers.secrets_router import router as secrets_router  # noqa: E402
from routers.server_credentials_router import router as server_credentials_router  # noqa: E402
from routers.downloads_router import router as downloads_router  # noqa: E402
from routers.types_router import router as types_router  # noqa: E402
from routers.artifacts_router import router as artifacts_router  # noqa: E402
from routers.gate_router import gate_router  # noqa: E402
from routers.beacon_router import beacon_router  # noqa: E402
from routers.search_router import search_router  # noqa: E402
from routers.events_router import router as events_router  # noqa: E402
from routers.internal_personas_router import router as internal_personas_router  # noqa: E402
from routers.stream_router import router as stream_router  # noqa: E402
from kernel import config  # noqa: E402
<<<<<<< Updated upstream
=======
from kernel.logging_utils import SuppressNoisyAccessFilter, build_log_config, configure_logging  # noqa: E402
>>>>>>> Stashed changes

# ----------------------------
# Logging setup (pre-Phase 2 — uses hardcoded defaults until config loads)
# ----------------------------
debug_level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
# Apply the shared logging config in-process so timestamps land on uvicorn's
# own startup + access lines regardless of the --log-config CLI flag.
configure_logging()
logger = logging.getLogger("agience.api")

logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)


class _MCPClosedResourceFilter(logging.Filter):
    """Suppress benign ClosedResourceError noise from MCP SDK."""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            exc = record.exc_info[1]
            if type(exc).__name__ == "ClosedResourceError":
                return False
        return True


class _EventsEmitAccessFilter(logging.Filter):
    """Suppress POST /events/emit from uvicorn access log.

    Chat streaming emits dozens of delta events per turn; logging every one
    drowns out useful access log entries.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "POST /events/emit" in msg:
            return False
        return True


logging.getLogger("mcp.server.streamable_http").addFilter(_MCPClosedResourceFilter())
logging.getLogger("uvicorn.access").addFilter(_EventsEmitAccessFilter())
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("httpx._client").setLevel(logging.ERROR)
# OpenSearch retired in Step 2.6.9 — no library logger to silence.

# ----------------------------
# Build Info
# ----------------------------
BUILD_INFO_PATH = os.getenv("BUILD_INFO_PATH", "/app/build_info.json")

def _load_build_info():
    for candidate in [BUILD_INFO_PATH, str(Path(__file__).resolve().parent.parent / "build_info.json")]:
        try:
            return json.loads(Path(candidate).read_text(encoding="utf-8"))
        except Exception:
            continue
    return {"version": "", "build_time": ""}

BUILD_INFO = _load_build_info()

# Setup mode is gone after 1.1e — Origin owns the setup wizard. The flag is
# kept at False so legacy references (root status, MCP discovery) keep
# returning "ok". The setup_mode_middleware below is now a no-op.
_setup_mode = False


def _run_phase4_core_sync(loop) -> None:
    """Run core Phase 4 initialization (ArangoDB, seeding, operator bootstrap).

    Called from run_phase4_after_setup() via asyncio.to_thread(). Completing
    this function is sufficient to unblock platform routes (_setup_mode = False).
    OpenSearch initialization runs separately in _run_phase4_search_sync.
    """
    from kernel.key_manager import delete_setup_token as _delete_setup_token
    _delete_setup_token()

    arango_db = init_arango_db()

    try:
        from services.platform_topology import pre_resolve_platform_ids
        pre_resolve_platform_ids(arango_db)
        from services import server_registry
        server_registry.populate_ids()
    except Exception:
        logger.exception("Platform ID pre-resolution failed at startup (fatal)")
        raise

    # Start the index worker before seeding (same reason as in the main lifespan
    # path) so that enqueue_index_artifact() is async.  Idempotent if already running.
    try:
        start_index_worker()
    except Exception as e:
        logger.error("Failed to start index worker before post-setup seeding: %s", e)

    # Load platform settings so the bootstrap flag is readable.  Safe to call
    # again — platform_settings.load_all() overwrites the in-memory cache from DB.
    from services.platform_settings_service import settings as platform_settings
    platform_settings.load_all(arango_db)

    # Seed provisioning runs only once — on a fresh DB (post first-time setup).
    # After the first successful run, platform.bootstrap.seeded is set so future
    # calls to this function (or normal lifespan restarts) skip seeding entirely.
    _platform_seeded = platform_settings.get_bool("platform.bootstrap.seeded", default=False)
    if not _platform_seeded:
        _run_platform_seed(arango_db)
        try:
            platform_settings.set_setting(
                arango_db,
                key="platform.bootstrap.seeded",
                value="true",
                category="bootstrap",
            )
            logger.info("Platform bootstrap complete — seed provisioning will be skipped on future restarts.")
        except Exception:
            logger.warning("Failed to persist platform.bootstrap.seeded flag (non-fatal)", exc_info=True)
    else:
        logger.info("Platform already seeded — skipping seed provisioning.")

    # Operator bootstrap runs on EVERY startup (idempotent; no-op until the
    # operator exists), decoupled from the one-time data-seed flag so the admin
    # gets its grants whenever it first appears (manifest at boot, or post-wizard).
    try:
        _ensure_operator_bootstrapped(arango_db)
    except Exception:
        logger.exception("Operator bootstrap failed at startup (non-fatal)")

    from kernel import event_bus
    event_bus.set_event_loop(loop)

    # Register built-in operation dispatch handlers (mcp_tool, native, artifact_crud).
    # Part of the Phase 0 Enterprise Eventing refactor: the operation dispatcher
    # reads `operations.*.dispatch.kind` from type.json and looks up the handler here.
    try:
        from services import handler_registry
        handler_registry.register_builtin_handlers()
    except Exception:
        logger.exception("Operation handler registry bootstrap failed at startup (non-fatal)")

    # Ensure the content bucket exists post-setup (config.CONTENT_URI is now set
    # from the settings written by the setup wizard).
    try:
        from services.content_service import reinit_edge_clients, ensure_content_bucket
        reinit_edge_clients()
        ensure_content_bucket()
    except Exception:
        logger.warning("Content bucket provisioning after setup failed (non-fatal)", exc_info=True)


def _run_phase4_search_sync(*, is_post_setup: bool = False) -> None:
    """Run search init + index-worker startup.

    Post-OpenSearch retirement (Step 2.6.9): no index creation step,
    no security provisioning. The encrypted MANTLE + SSE indexes
    bootstrap lazily on first commit. The only lifecycle work is the
    async index queue's worker.
    """
    init_search()
    try:
        start_index_worker()
    except Exception as e:
        logger.error("Failed to start indexing worker: %s", e)

    # Post-setup reindex: any seed content created before the indexer
    # came online needs a one-shot pass through the encrypted indexes.
    if is_post_setup:
        logger.info("Post-setup: reindexing all artifacts (background)...")
        reindex_in_background()


async def run_phase4_after_setup() -> None:
    """Run Phase 4 initialization in the background after setup completes.

    Called from the setup complete endpoint as a background task instead of
    restarting the process. The MCP server session manager is already running
    from Phase 3 so that step is skipped.

    Sets _setup_mode = False after core init (ArangoDB + seeding) so the
    frontend redirects promptly. Search init runs in background.
    """
    global _setup_mode
    logger.info("Phase 4 initialization starting (post-setup).")
    try:
        loop = asyncio.get_running_loop()
        await asyncio.to_thread(_run_phase4_core_sync, loop)
        _setup_mode = False
        logger.info("Phase 4 core complete — platform routes unblocked.")
        # Background reindex of any seed content created during setup.
        asyncio.create_task(_run_phase4_search_async(is_post_setup=True))
    except Exception:
        logger.exception("Phase 4 initialization failed after setup.")


async def _run_phase4_search_async(*, is_post_setup: bool = False) -> None:
    """Run search initialization in background without blocking platform routes."""
    try:
        await asyncio.to_thread(_run_phase4_search_sync, is_post_setup=is_post_setup)
        logger.info("Phase 4 search initialization complete.")
    except Exception:
        logger.exception("Phase 4 search initialization failed (non-fatal).")


def _ensure_operator_bootstrapped(arango_db) -> None:
    """Bootstrap the designated platform admin user's Arango resources.

    The platform admin is simply the user designated by ``platform.operator_id``
    — grants are uniform (there is no operator grant *type* or condition). Runs
    on every startup, idempotent, no-op until that user exists:

    1. Creates their personal collection.
    2. Provisions them via ``provision_user``, which applies the per-user grant
       seeds and — because they are the designated admin — the admin grant seeds
       (``package/seeds/admin``: full management access on platform collections).
    """
    from services.platform_settings_service import settings as platform_settings

    operator_id = platform_settings.get("platform.operator_id")
    if not operator_id:
        # Mantle's ArangoDB platform_settings may not hold platform.operator_id
        # (e.g. after a factory reset that wiped ArangoDB but left Origin intact).
        # Ask Origin directly — non-fatal if Origin is not yet reachable.
        try:
            from clients.origin_client import get_origin_client
            operator_id = get_origin_client().get_operator_id()
        except Exception:
            logger.debug("Could not fetch operator_id from Origin at startup (non-fatal)", exc_info=True)
    if not operator_id:
        return  # No platform admin designated yet (setup not complete)

    from db.arango import get_collection_by_id
    from services.collection_service import create_new_collection

    # 1. Personal collection (id == owner_id by convention).
    if not get_collection_by_id(arango_db, operator_id):
        try:
            create_new_collection(
                db=arango_db,
                owner_id=operator_id,
                name="Personal",
                description="Default personal collection",
                is_personal=True,
            )
            logger.info("Created personal collection for platform admin %s", operator_id)
        except Exception:
            logger.warning("Could not create personal collection for platform admin %s", operator_id, exc_info=True)

    # 2. Provision the admin like any user; provision_user recognises the
    #    designated admin and additionally applies the admin grant seeds.
    try:
        from services.seed_provisioning import provision_user
        provision_user(arango_db, operator_id)
        logger.info("Provisioned platform admin %s", operator_id)
    except Exception:
        logger.warning("Provisioning failed for platform admin %s (non-fatal)", operator_id, exc_info=True)


def _run_platform_seed(arango_db) -> None:
    """Seed the platform DATA (collections, artifacts, edges) once on a fresh DB
    by applying the ``package/seeds/platform`` tree via the loader, then refresh
    the server registry's name→id map (server UUIDs are minted by the loader,
    not pre-resolved).

    Operator bootstrap is intentionally NOT here: it must run on every startup
    (decoupled from the one-time seed flag) so the admin gets grants whenever it
    first exists — see the call to `_ensure_operator_bootstrapped` in the seed
    paths below."""
    from pathlib import Path as _SeedPath
    from services import seed_provisioning, server_registry

    seeds_root = _SeedPath(os.getenv("AGIENCE_SEEDS_ROOT") or str(config.BASE_DIR / "package" / "seeds"))
    report = seed_provisioning.seed_from_artifacts(arango_db, seeds_root / "platform")
    logger.info("Platform seed: %s", report.summary())
    for err in report.errors:
        logger.warning("platform seed: %s", err)

    # The loader registers + persists platform/server UUIDs; refresh the
    # registry's reverse index so name→id lookups resolve this boot.
    server_registry.populate_ids()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _setup_mode

    # ------------------------------------------------------------------
    # Phase 0: Initialize all key material (filesystem)
    # ------------------------------------------------------------------
    try:
        from kernel.key_manager import (
            init_licensing_keys,
            init_encryption_key,
            init_setup_token,
            init_arango_password, init_minio_password,
            init_nonce_secret,
        )
        from kernel import service_identity

        init_licensing_keys()
        init_encryption_key()
        init_nonce_secret()
        init_setup_token()
        init_arango_password()
        init_minio_password()
        # Phase C — Mantle signs its own service-to-service JWTs with mantle.private.pem.
        # Mantle does NOT sign user tokens (only Origin does); peer JWTs are verified
        # via the inline JWKS in the platform authority manifest.
        service_identity.init_service_identity("mantle")
    except Exception:
        logger.exception("Key initialization failed at startup (fatal)")
        raise

    # ------------------------------------------------------------------
    # Phase 1.5: Load bootstrap settings from key files
    # ------------------------------------------------------------------
    config.load_bootstrap_settings()
    from services.content_service import reinit_edge_clients
    reinit_edge_clients()

    # ------------------------------------------------------------------
    # Phase 2: Connect to databases, load platform settings
    # ------------------------------------------------------------------
    # Initialize ArangoDB (creates collections/indexes) — needed early
    # because platform settings now live in ArangoDB.
    arango_db = init_arango_db()

    # Load platform settings from ArangoDB into cache
    from services.platform_settings_service import settings as platform_settings
    platform_settings.load_all(arango_db)

    # Rebind config module variables from DB settings
    config.load_settings_from_db()

    # Re-initialize edge S3 clients now that config.CONTENT_URI is set from DB,
    # then eagerly ensure the content bucket exists.
    from services.content_service import reinit_edge_clients, ensure_content_bucket
    reinit_edge_clients()
    try:
        ensure_content_bucket()
    except Exception:
        logger.warning("Content bucket check at startup failed (non-fatal)", exc_info=True)

    # OAuth provider registration moved to Origin in 1.1a-ii. Mantle no longer
    # serves /auth/authorize or /auth/callback.

    # Reconfigure logging with DB-loaded log level
    log_level = (config.BACKEND_LOG_LEVEL or "info").upper()
    logging.getLogger().setLevel(debug_level_map.get(log_level, logging.INFO))

    # ------------------------------------------------------------------
    # Phase 3 — setup gate is gone after 1.1e. Origin owns the setup wizard;
    # Mantle just starts up. Operators see setup state via Origin's /setup/status.
    # ------------------------------------------------------------------
    _setup_mode = False

    # init_setup_token() in Phase 0 recreates the file if it was deleted by
    # delete_setup_token() during setup completion.  Clean it up now that we
    # know setup is done so no orphan token lingers on disk between restarts.
    from kernel.key_manager import delete_setup_token as _delete_setup_token
    _delete_setup_token()

    # arango_db already initialized in Phase 2

    # Pre-resolve platform singleton IDs (in-memory cache, needed on every startup)
    try:
        from services.platform_topology import pre_resolve_platform_ids
        pre_resolve_platform_ids(arango_db)
        from services import server_registry
        server_registry.populate_ids()
    except Exception:
        logger.exception("Platform ID pre-resolution failed at startup (fatal)")
        raise

    # Start the index worker before seeding so that enqueue_index_artifact()
    # dispatches to the async queue rather than falling back to synchronous
    # per-artifact blocking. init_search() is a no-op post-OpenSearch; the
    # later _run_phase4_search_async task will skip re-starting an already
    # running worker (IndexQueue.start() is idempotent).
    try:
        start_index_worker()
    except Exception as e:
        logger.error("Failed to start index worker before seeding: %s", e)

    # Seed provisioning runs only once — on a fresh DB (reset).  After the
    # first successful run, platform.bootstrap.seeded is persisted in
    # platform_settings so restarts skip this block entirely.  A --reset wipes
    # ArangoDB, which removes the flag, causing seeding to run again.
    _platform_seeded = platform_settings.get_bool("platform.bootstrap.seeded", default=False)
    if not _platform_seeded:
        _run_platform_seed(arango_db)
        try:
            platform_settings.set_setting(
                arango_db,
                key="platform.bootstrap.seeded",
                value="true",
                category="bootstrap",
            )
            logger.info("Platform bootstrap complete — seed provisioning will be skipped on future restarts.")
        except Exception:
            logger.warning("Failed to persist platform.bootstrap.seeded flag (non-fatal)", exc_info=True)
    else:
        logger.info("Platform already seeded — skipping seed provisioning.")

    # Operator bootstrap runs on EVERY startup (idempotent; no-op until the
    # operator exists), decoupled from the one-time data-seed flag so the admin
    # gets its grants whenever it first appears (manifest at boot, or post-wizard).
    try:
        _ensure_operator_bootstrapped(arango_db)
    except Exception:
        logger.exception("Operator bootstrap failed at startup (non-fatal)")

    # Event bus — must be set before requests are served
    from kernel import event_bus
    event_bus.set_event_loop(asyncio.get_event_loop())

    # Register built-in operation dispatch handlers (mcp_tool, native, artifact_crud).
    try:
        from services import handler_registry
        handler_registry.register_builtin_handlers()
    except Exception:
        logger.exception("Operation handler registry bootstrap failed at startup (non-fatal)")

    # Search init in background (lazy bootstrap; won't block).
    # Pass is_post_setup=True when seeding just ran so reindex_in_background()
    # is triggered — seed sub-collection containers are indexed at creation time
    # but any that were skipped (e.g. S3 not ready) will be caught here.
    search_init_task = asyncio.create_task(_run_phase4_search_async(is_post_setup=not _platform_seeded))

    yield

    # Cleanup on shutdown
    search_init_task.cancel()
    try:
        await search_init_task
    except (asyncio.CancelledError, Exception):
        pass
    try:
        stop_index_worker(drain=True, timeout=5.0)
    except Exception as e:
        logger.error(f"Failed to stop indexing worker: {e}")
    shutdown_search()

# ----------------------------
# Create app
# ----------------------------
app = FastAPI(
    title="Agience API",
    version=BUILD_INFO.get("version") or "unknown",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
    swagger_ui_init_oauth={
        "clientId": "agience-docs-client",
        "usePkceWithAuthorizationCodeGrant": True,
    },
)

try:
    app.router.redirect_slashes = False
except Exception:
    pass

# ----------------------------
# Setup mode middleware
# ----------------------------
_SETUP_ALLOWED_PREFIXES = ("/setup", "/version", "/.well-known", "/docs", "/openapi.json", "/auth/token", "/server-credentials")

@app.middleware("http")
async def setup_mode_middleware(request: Request, call_next):
    """When in setup mode, only allow setup-related routes."""
    if _setup_mode:
        path = request.url.path
        if path == "/" or any(path.startswith(prefix) for prefix in _SETUP_ALLOWED_PREFIXES):
            return await call_next(request)
        return JSONResponse(
            status_code=503,
            content={"detail": "Setup required", "setup_url": "/setup"},
        )
    return await call_next(request)

# ----------------------------
# Error logging handlers
# ----------------------------

# Fields whose values must never appear in logs.
_REDACT_KEYS = frozenset({"password", "secret", "token", "api_key", "apikey",
                          "access_token", "refresh_token", "credential",
                          "passkey_credential", "passkey_challenge"})

def _redact_body(raw: bytes, max_len: int = 2048) -> str:
    """Return a log-safe representation of a request body.

    JSON bodies have sensitive fields replaced with '***'. Non-JSON
    bodies are truncated to *max_len* bytes.
    """
    if not raw:
        return ""
    try:
        import json as _json
        obj = _json.loads(raw)
        if isinstance(obj, dict):
            obj = {k: ("***" if k.lower() in _REDACT_KEYS else v)
                   for k, v in obj.items()}
        return _json.dumps(obj, ensure_ascii=False)[:max_len]
    except Exception:
        return repr(raw[:max_len])


@app.exception_handler(HTTPException)
async def http_exception_logger(request: Request, exc: HTTPException):
    try:
        body = await request.body()
    except Exception:
        body = b""
    logger.warning(
        "HTTP %s %s %s user=%s ws=%s artifact=%s detail=%r body=%s",
        exc.status_code,
        request.method,
        request.url.path,
        getattr(request.state, "user_id", None),
        request.path_params.get("workspace_id"),
        request.path_params.get("artifact_id"),
        exc.detail,
        _redact_body(body),
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(Exception)
async def unhandled_exception_logger(request: Request, exc: Exception):
    try:
        body = await request.body()
    except Exception:
        body = b""
    logger.exception(
        "HTTP 500 %s %s user=%s ws=%s artifact=%s body=%s error=%s",
        request.method,
        request.url.path,
        getattr(request.state, "user_id", None),
        request.path_params.get("workspace_id"),
        request.path_params.get("artifact_id"),
        _redact_body(body),
        repr(exc),
    )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

# ----------------------------
# CORS & Session
# ----------------------------
# allow_origins=["*"] is safe: all authenticated API calls use Bearer tokens,
# not cookies, so cross-origin requests without credentials pose no CSRF risk.
# The OAuth redirect flow uses session cookies but those are same-site
# (browser navigations, not XHR), so CORS doesn't apply to them.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# SessionMiddleware moved to Origin alongside the OAuth flows. Mantle no longer
# carries the OAuth PKCE state cookie because it no longer serves /auth/authorize.

# ----------------------------
# Routers
# ----------------------------
app.include_router(server_credentials_router)
app.include_router(secrets_router)
app.include_router(downloads_router)
app.include_router(events_router)
app.include_router(types_router)
app.include_router(artifacts_router)
app.include_router(gate_router)
app.include_router(beacon_router)
app.include_router(search_router)
app.include_router(internal_personas_router)
app.include_router(stream_router)

# ----------------------------
# MCP surface moved to chorus's universal gateway. Clients address Mantle's
# kernel ops at chorus.example.com/{kernel_artifact_id}/mcp via the
# `core` persona registered in chorus/manifest.json. Mantle itself no
# longer publishes /mcp — see .dev/features/mantle-mcp-consolidation.md.

# ----------------------------
# Basic routes
# ----------------------------
def utcnow_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

@app.get("/", include_in_schema=False)
def read_root():
    payload = {
        "status": "ok" if not _setup_mode else "setup_required",
        "version": BUILD_INFO.get("version") or "unknown",
        "server_time": utcnow_z(),
        "links": {
            "self": "/",
            "service-doc": "/docs",
            "service-desc": "/openapi.json",
        },
    }
    return JSONResponse(
        content=payload,
        status_code=200,
        headers={"Cache-Control": "no-store"}
    )

@app.get("/status", include_in_schema=False)
def check_backend_status():
    status = {
        **check_arango_health(),
    }
    return status

@app.get("/version", include_in_schema=False)
def version():
    return {
        "version": BUILD_INFO.get("version") or "",
        "build_time": BUILD_INFO.get("build_time") or ""
    }

# ----------------------------
# Entrypoint (dev)
# ----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8081,
        reload=True,
        reload_dirs=["mantle", "kernel"],
        reload_excludes=["**/__pycache__/*", "**/*.pyc"],
        log_level="info",
        log_config=build_log_config(),
        workers=1,
        server_header=False,
        timeout_graceful_shutdown=3,
    )
