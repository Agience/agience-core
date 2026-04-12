from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from types import ModuleType

from fastapi import FastAPI

from .config import DesktopRelayHostConfig
from .desktop_host_server import create_desktop_host_server
from .host_service import DesktopHostService
from .local_policy import LocalPolicy
from .relay_client import RelayClient
from .relay_runtime import RelayRuntimeHandler
from .relay_state import RelayState
from .supervisor import LocalServerSupervisor

log = logging.getLogger("agience-relay-desktop.host")

PERSONA_PATHS = {
    "aria": Path("servers/aria/server.py"),
    "sage": Path("servers/sage/server.py"),
    "atlas": Path("servers/atlas/server.py"),
    "nexus": Path("servers/nexus/server.py"),
    "astra": Path("servers/astra/server.py"),
    "verso": Path("servers/verso/server.py"),
    "seraph": Path("servers/seraph/server.py"),
    "ophan": Path("servers/ophan/server.py"),
}


def create_host_app(config: DesktopRelayHostConfig) -> FastAPI:
    policy = LocalPolicy(config.allowed_roots)
    supervisor = LocalServerSupervisor(config.service_definitions_dir)
    service = DesktopHostService(config, policy, supervisor)
    desktop_host_server = create_desktop_host_server(config, service)
    relay_runtime = RelayRuntimeHandler(service)
    relay_state = RelayState(config.authority_url, configured=bool(config.authority_url and config.access_token))
    relay_client = RelayClient(config, relay_runtime, relay_state)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop_event = asyncio.Event()
        relay_task = None
        if relay_client.enabled:
            relay_task = asyncio.create_task(relay_client.run_forever(stop_event))
        try:
            yield
        finally:
            stop_event.set()
            if relay_task is not None:
                relay_task.cancel()
                with suppress(asyncio.CancelledError):
                    await relay_task

    app = FastAPI(title="Agience Desktop Relay Host", lifespan=lifespan)

    app.state.desktop_relay_config = config
    app.state.local_policy = policy
    app.state.local_supervisor = supervisor
    app.state.desktop_host_service = service
    app.state.relay_state = relay_state
    app.state.relay_client = relay_client

    app.mount("/desktop-host", desktop_host_server.streamable_http_app())

    for persona in config.enabled_personas:
        module = load_persona_module(persona)
        app.mount(f"/{persona}", _resolve_persona_app(module))

    @app.get("/")
    def index() -> dict[str, object]:
        persona_servers = [
            {
                "name": persona,
                "endpoint": f"/{persona}/mcp",
            }
            for persona in config.enabled_personas
        ]
        return {
            "service": "agience-relay-desktop",
            "mode": config.mode.value,
            "relay_server_id": config.relay_server_id,
            "authority_url": config.authority_url,
            "servers": [
                {
                    "name": config.relay_server_id,
                    "endpoint": "/desktop-host/mcp",
                },
                *persona_servers,
            ],
        }

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/local/servers")
    def local_servers() -> dict[str, object]:
        return {"servers": supervisor.list_servers()}

    @app.get("/relay/status")
    def relay_status() -> dict[str, object]:
        return relay_state.as_dict()

    return app


def load_persona_module(persona: str) -> ModuleType:
    if persona not in PERSONA_PATHS:
        known = ", ".join(sorted(PERSONA_PATHS))
        raise ValueError(f"Unknown persona '{persona}'. Expected one of: {known}.")

    repo_root = _repo_root()
    module_path = repo_root / PERSONA_PATHS[persona]
    module_name = f"agience_desktop_persona_{persona}"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load persona module '{persona}' from {module_path}.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_persona_app(module: ModuleType):
    if hasattr(module, "streamable_http_app"):
        return module.streamable_http_app()

    mcp = getattr(module, "mcp", None)
    if mcp is not None:
        return mcp.streamable_http_app()

    raise RuntimeError(f"Loaded module '{module.__name__}' does not expose an MCP app.")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]