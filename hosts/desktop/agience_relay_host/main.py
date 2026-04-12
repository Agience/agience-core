from __future__ import annotations

import argparse
import logging

import uvicorn

from .config import DesktopRelayHostConfig
from .runtime_modes import RelayRuntimeMode
from .source_host_app import create_host_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Agience desktop relay host runtime.")
    parser.add_argument("--config", help="Optional path to a JSON config file.")
    parser.add_argument("--mode", choices=[mode.value for mode in RelayRuntimeMode])
    parser.add_argument("--authority-url")
    parser.add_argument("--bind-host")
    parser.add_argument("--bind-port", type=int)
    parser.add_argument("--personas", help="Comma-separated list of enabled persona servers.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = DesktopRelayHostConfig.from_file(args.config) if args.config else DesktopRelayHostConfig.from_env()
    config = _apply_overrides(config, args)

    logging.basicConfig(level=config.log_level)

    if config.mode is RelayRuntimeMode.AUTHORITY:
        raise SystemExit(
            "Authority mode is reserved for the future full control-plane runtime. "
            "Use '--mode host' for the desktop relay host."
        )

    app = create_host_app(config)
    uvicorn.run(app, host=config.bind_host, port=config.bind_port, log_level=config.log_level.lower())
    return 0


def _apply_overrides(config: DesktopRelayHostConfig, args: argparse.Namespace) -> DesktopRelayHostConfig:
    payload = {
        "mode": args.mode or config.mode.value,
        "authority_url": args.authority_url if args.authority_url is not None else config.authority_url,
        "access_token": config.access_token,
        "client_version": config.client_version,
        "heartbeat_interval_seconds": config.heartbeat_interval_seconds,
        "reconnect_delay_seconds": config.reconnect_delay_seconds,
        "bind_host": args.bind_host or config.bind_host,
        "bind_port": args.bind_port or config.bind_port,
        "display_name": config.display_name,
        "device_id": config.device_id,
        "relay_server_id": config.relay_server_id,
        "allowed_roots": config.allowed_roots,
        "service_definitions_dir": config.service_definitions_dir,
        "enabled_personas": args.personas.split(",") if args.personas else config.enabled_personas,
        "log_level": config.log_level,
    }
    return DesktopRelayHostConfig.from_mapping(payload)


if __name__ == "__main__":
    raise SystemExit(main())