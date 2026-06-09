"""
servers-host — Unified MCP server host
================================================
Mounts all Agience server personas into a single FastAPI process.

Endpoints (each FastMCP app serves at /<name>/mcp):
  /aria/mcp    — Aria   (Presentation & Interface)
  /sage/mcp    — Sage   (Research & Retrieval)
  /iris/mcp    — Iris   (Routing & Communication)
  /astra/mcp   — Astra  (Ingestion & Indexing)
  /verso/mcp   — Verso  (Reasoning & Workflow)
  /seraph/mcp  — Seraph (Security & Governance)
  /ophan/mcp   — Ophan  (Economic Operations)

Astra also serves SRS stream webhook routes at /astra/stream/*.

All reachable on a single port (default: 8082).

Config:
  MCP_HOST               — Bind host (default: 0.0.0.0)
  MCP_PORT               — Bind port (default: 8082)
  LOG_LEVEL              — Logging level (default: INFO)
"""

from __future__ import annotations

import contextlib
import importlib.util
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType

import uvicorn
from fastapi import FastAPI

log = logging.getLogger("servers-host")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s - %(name)s - %(message)s")

# Suppress noisy per-request httpx/uvicorn logs (dozens of events/emit per chat turn)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

MCP_HOST: str = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT: int = int(os.getenv("MCP_PORT", "8082"))
HOST_DIR = Path(__file__).resolve().parent

# Make the shared auth module + the kernel package importable before any
# persona module loads. Persona modules import `agience_server_auth` at the
# top level, and `agience_server_auth` in turn imports `kernel.service_identity`
# and `kernel.authority_trust`.
#
# Layout:
#  mantle/ chorus/server.py    ← __file__
#  mantle/ chorus/_shared/     ← agience_server_auth, mantle_client, gateway_middleware
#  mantle/ kernel/             ← service_identity, authority_trust, config
#
# In docker, persona modules are copied flat into /app/ so this manipulation
# is harmless.
_shared_dir = str(HOST_DIR / "_shared")
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)
_kernel_parent = str(HOST_DIR.parent)  #mantle/   — so `from kernel import ...` resolves
if _kernel_parent not in sys.path:
    sys.path.insert(0, _kernel_parent)

# Phase C: load the chorus service identity once at process boot, before any
# persona AgieceServerAuth instance is constructed. Each persona signs its own
# kernel JWTs with this key (sub=persona_client_id, iss=chorus, aud=mantle).
# The init container writes chorus.private.pem into KEYS_DIR.
from kernel import service_identity  # noqa: E402

service_identity.init_service_identity("chorus")
log.info("Chorus service identity loaded — kid=chorus-1")

# ---------------------------------------------------------------------------
# Import each server module.
#
# Two layouts are supported:
#   - Local dev: mantle/ chorus/server.py  →  sibling subdirs atmantle/ chorus/<name>/server.py
#   - Docker:     /app/server.py        →  flat /app/<name>_server.py files
#
# Phase G.3 cleanup: the local-layout detection used to require a `_host/`
# subdir name, which never matched the actual layout. Now we just check
# whether the persona subdir exists directly.
# ---------------------------------------------------------------------------

_LOCAL_LAYOUT = (HOST_DIR / "aria" / "server.py").exists()

if _LOCAL_LAYOUT:
    SERVERS_DIR = HOST_DIR

    def _load_module(module_name: str, file_path: Path, *extra_paths: Path) -> ModuleType:
        search_paths = [file_path.parent, *extra_paths]
        for path in reversed(search_paths):
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load module {module_name!r} from {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    log.info("Local layout detected — loading server modules from %s", SERVERS_DIR)
    aria_server = _load_module("servers_host_aria_server", SERVERS_DIR / "aria" / "server.py")
    astra_server = _load_module("servers_host_astra_server", SERVERS_DIR / "astra" / "server.py")
    sage_server = _load_module("servers_host_sage_server", SERVERS_DIR / "sage" / "server.py")
    iris_server = _load_module("servers_host_iris_server", SERVERS_DIR / "iris" / "server.py")
    ophan_server = _load_module("servers_host_ophan_server", SERVERS_DIR / "ophan" / "server.py")
    seraph_server = _load_module("servers_host_seraph_server", SERVERS_DIR / "seraph" / "server.py")
    verso_server = _load_module("servers_host_verso_server", SERVERS_DIR / "verso" / "server.py")
else:
    log.info("Flat layout detected — importing server modules directly")
    import aria_server    # type: ignore[import-not-found]  # noqa: E402
    import astra_server   # type: ignore[import-not-found]  # noqa: E402
    import sage_server   # type: ignore[import-not-found]  # noqa: E402
    import iris_server    # type: ignore[import-not-found]  # noqa: E402
    import ophan_server   # type: ignore[import-not-found]  # noqa: E402
    import seraph_server  # type: ignore[import-not-found]  # noqa: E402
    import verso_server   # type: ignore[import-not-found]  # noqa: E402

# ---------------------------------------------------------------------------
# Step 3 — Verso runtime swap.
#
# The premium build sets VERSO_PACKAGE at build time (which pip-installs
# the closed-source wheel) and VERSO_MODULE at runtime (the import name
# the wheel exposes). When VERSO_PACKAGE is non-empty AND the named
# module imports cleanly, route Verso through it. Otherwise the bundled
# public verso_server stays in place — same image, same Dockerfile.
# ---------------------------------------------------------------------------

_verso_package = (os.getenv("VERSO_PACKAGE") or "").strip()
_verso_module_name = (os.getenv("VERSO_MODULE") or "").strip()
if _verso_package and _verso_module_name:
    try:
        import importlib as _importlib
        _premium = _importlib.import_module(_verso_module_name)
        log.info(
            "Loaded premium Verso runtime: package=%s module=%s",
            _verso_package, _verso_module_name,
        )
        verso_server = _premium  # noqa: F811 — intentional override
    except ImportError as exc:
        log.error(
            "VERSO_PACKAGE=%s set but module %s could not be imported: %s "
            "— falling back to bundled public Verso",
            _verso_package, _verso_module_name, exc,
        )


# ---------------------------------------------------------------------------
# FastAPI host
# ---------------------------------------------------------------------------

# Build the Starlette sub-apps and collect their session managers so we can
# explicitly run them during the host lifespan.  Mounted sub-apps' lifespans
# are not reliably triggered by the parent FastAPI app, which causes FastMCP's
# StreamableHTTPSessionManager task group to never start (RuntimeError:
# "Task group is not initialized").

_MCP_MODULES = [
    aria_server, astra_server, sage_server,
    iris_server, ophan_server, seraph_server, verso_server,
]

_sub_apps: dict[str, object] = {}
_session_managers: list[object] = []
_startup_fns: list[object] = []

for _mod in _MCP_MODULES:
    # Individual server FastMCP instances default to host="127.0.0.1", which
    # causes MCP SDK >=1.23 to auto-enable DNS rebinding protection (only
    # allowing 127.0.0.1/localhost as Host headers).  In host mode *this*
    # process binds on 0.0.0.0 and is reached via Docker DNS ("servers:8082"),
    # so the per-server restriction must be cleared before we build the app.
    if getattr(_mod.mcp.settings, "transport_security", None) is not None:
        _mod.mcp.settings.transport_security = None
    create_fn = getattr(_mod, "create_server_app", None)
    _sub_app = create_fn() if create_fn else _mod.mcp.streamable_http_app()
    _name = _mod.mcp.name.replace("agience-server-", "")
    _sub_apps[_name] = _sub_app
    if _mod.mcp._session_manager is not None:
        _session_managers.append(_mod.mcp._session_manager)
    startup_fn = getattr(_mod, "server_startup", None)
    if startup_fn is not None:
        _startup_fns.append(startup_fn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    for startup_fn in _startup_fns:
        await startup_fn()
    async with contextlib.AsyncExitStack() as stack:
        for sm in _session_managers:
            await stack.enter_async_context(sm.run())
        yield


app = FastAPI(title="Agience Servers", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Phase E — Universal MCP gateway middleware
#
# Intercepts requests of shape `/{server_id}/mcp...` where `server_id` is a
# UUID. Resolves the UUID to a persona slug via the deployment's slug→UUID
# map (fetched lazily from Mantle's `/internal/personas`), then rewrites the
# path so the existing slug-mounted sub-app handles the request.
#
# Persona slugs are baked into the chorus image; UUIDs are deployment-specific
# random values from `platform_topology` (Mantle-side). Chorus has no way to
# compute them locally — it must fetch the map.
# ---------------------------------------------------------------------------

from mantle_client import get_gateway_client  # type: ignore[import-not-found]  # noqa: E402
from gateway_middleware import (  # type: ignore[import-not-found]  # noqa: E402
    PersonaMap,
    UniversalMCPGatewayMiddleware,
)
from relay_manager import get_relay_manager  # type: ignore[import-not-found]  # noqa: E402


_PERSONA_SLUGS = {"aria", "sage", "iris", "astra", "verso", "seraph", "ophan"}
_persona_map = PersonaMap(gateway_client_factory=get_gateway_client)
_relay_manager = get_relay_manager()


def _resolve_user_id_from_scope(scope: dict) -> str | None:
    """Extract `sub` from the inbound delegation JWT for relay dispatch.

    Trusts the bearer token without re-verification — the persona's middleware
    re-verifies before any state mutation. The relay manager only uses this to
    pick the correct WS session.
    """
    headers = scope.get("headers") or []
    raw_auth = ""
    for k, v in headers:
        if k.lower() == b"authorization":
            raw_auth = v.decode("latin-1", errors="ignore")
            break
    if not raw_auth.lower().startswith("bearer "):
        return None
    token = raw_auth[7:].strip()
    if not token or token.count(".") != 2:
        return None
    # Decode the payload segment without verification — relay routing only.
    import base64 as _b64
    import json as _json
    try:
        _, payload, _ = token.split(".", 2)
        padding = "=" * (4 - len(payload) % 4)
        decoded = _b64.urlsafe_b64decode(payload + padding)
        claims = _json.loads(decoded)
    except (ValueError, UnicodeDecodeError):
        return None
    sub = claims.get("sub")
    return str(sub) if sub else None


app.add_middleware(
    UniversalMCPGatewayMiddleware,
    persona_map=_persona_map,
    gateway_client_factory=get_gateway_client,
    local_persona_slugs=_PERSONA_SLUGS,
    relay_manager=_relay_manager,
    user_id_resolver=_resolve_user_id_from_scope,
)


# ---------------------------------------------------------------------------
# Relay WebSocket endpoint — desktop runtime connects here
# ---------------------------------------------------------------------------

from fastapi import WebSocket, WebSocketDisconnect  # noqa: E402
from kernel.authority_trust import verify_jwt as _verify_jwt  # noqa: E402
from jose.exceptions import JWTError  # noqa: E402


@app.websocket("/relay/v1/connect")
async def relay_connect(websocket: WebSocket) -> None:
    """Desktop runtime connects here to register an active relay session.

    Auth: user-token JWT signed by Origin. The handshake doesn't pre-verify
    `aud` since user tokens have variable audience; verification is signature-
    only via the authority manifest's inline JWKS for the `origin` anchor.
    """
    raw_auth = websocket.headers.get("authorization", "")
    if not raw_auth.lower().startswith("bearer "):
        await websocket.close(code=4401, reason="Missing bearer token")
        return
    token = raw_auth[7:].strip()
    try:
        claims = _verify_jwt(token, expected_issuer_service="origin")
    except (KeyError, JWTError):
        await websocket.close(code=4401, reason="Invalid bearer token")
        return
    user_id = claims.get("sub")
    if not user_id:
        await websocket.close(code=4401, reason="Token missing sub")
        return

    session = await _relay_manager.connect(websocket, user_id=str(user_id))
    try:
        while True:
            envelope = await websocket.receive_json()
            await _relay_manager.handle_response_envelope(session.session_id, envelope)
    except WebSocketDisconnect:
        pass
    finally:
        await _relay_manager.disconnect(session.session_id)

# Astra needs both stream webhook routes AND MCP protocol endpoints under
# /astra.  Wrap them in a single FastAPI app so both are reachable:
#   /astra/stream/*  → stream routes (SRS webhooks)
#   /astra/mcp       → MCP protocol
_astra_combined = FastAPI()
try:
    if _LOCAL_LAYOUT:
        _stream_routes_mod = _load_module(
            "servers_host_astra_stream_routes",
            SERVERS_DIR / "astra" / "stream_routes.py",
        )
    else:
        import stream_routes as _stream_routes_mod  # type: ignore[import-not-found]
    _astra_combined.include_router(_stream_routes_mod.router)
    log.info("Astra stream routes loaded")
except Exception as exc:
    log.warning("Astra stream routes not loaded: %s", exc)
_astra_combined.mount("/", _sub_apps["astra"])

app.mount("/aria",   _sub_apps["aria"])
app.mount("/sage",   _sub_apps["sage"])
app.mount("/iris",   _sub_apps["iris"])
app.mount("/astra",  _astra_combined)
app.mount("/verso",  _sub_apps["verso"])
app.mount("/seraph", _sub_apps["seraph"])
app.mount("/ophan",  _sub_apps["ophan"])


_PERSONAS = [
    {"name": "aria",   "endpoint": "/aria/mcp",   "role": "Presentation & Interface"},
    {"name": "sage",   "endpoint": "/sage/mcp",   "role": "Research & Retrieval"},
    {"name": "iris",   "endpoint": "/iris/mcp",   "role": "Routing & Communication"},
    {"name": "astra",  "endpoint": "/astra/mcp",  "role": "Ingestion & Indexing"},
    {"name": "verso",  "endpoint": "/verso/mcp",  "role": "Reasoning & Workflow"},
    {"name": "seraph", "endpoint": "/seraph/mcp", "role": "Security & Governance"},
    {"name": "ophan",  "endpoint": "/ophan/mcp",  "role": "Economic Operations"},
]


@app.get("/")
def index():
    return {
        "service": "chorus",
        "port": MCP_PORT,
        "servers": _PERSONAS,
    }


@app.get("/healthz", tags=["health"])
def healthz():
    return {"status": "ok"}


@app.get("/.well-known/mcp")
def well_known_mcp():
    """Per-deployment Chorus discovery.

    Surfaces both the slug-based routes (`/aria/mcp` etc.) and each persona's
    deployment-specific artifact UUID resolved from Mantle's `/internal/personas`.
    Callers can use either `POST /{slug}/mcp` or `POST /{uuid}/mcp` —
    the gateway middleware rewrites UUIDs to slugs internally.
    """
    if not _persona_map.loaded:
        _persona_map.refresh()
    uuid_map = {entry["slug"]: entry["artifact_id"] for entry in _persona_map.all_personas()}
    enriched = [{**p, "artifact_id": uuid_map.get(p["name"])} for p in _PERSONAS]
    return {
        "service": "chorus",
        "transport": "streamable-http",
        "discovery": {
            "personas": enriched,
            "uuid_routing_enabled": bool(uuid_map),
        },
    }


if __name__ == "__main__":
    log.info("Starting servers-host — host=%s port=%s", MCP_HOST, MCP_PORT)
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT, access_log=True)
