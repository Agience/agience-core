from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .runtime_modes import RelayRuntimeMode

DEFAULT_PERSONAS = (
    "aria",
    "sage",
    "atlas",
    "nexus",
    "astra",
    "verso",
    "seraph",
    "ophan",
)


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_PERSONAS
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _normalize_personas(values: Iterable[str] | None) -> tuple[str, ...]:
    if not values:
        return DEFAULT_PERSONAS
    return tuple(str(value).strip() for value in values if str(value).strip())


def _normalize_paths(values: Iterable[str] | None, fallback: Iterable[str] | None = None) -> tuple[Path, ...]:
    raw_values = list(values or fallback or [])
    normalized = [Path(str(value)).expanduser().resolve() for value in raw_values if str(value).strip()]
    return tuple(normalized)


@dataclass(frozen=True)
class DesktopRelayHostConfig:
    mode: RelayRuntimeMode
    authority_url: str | None
    access_token: str | None
    client_version: str
    heartbeat_interval_seconds: int
    reconnect_delay_seconds: int
    bind_host: str
    bind_port: int
    display_name: str
    device_id: str
    relay_server_id: str
    allowed_roots: tuple[Path, ...]
    service_definitions_dir: Path
    enabled_personas: tuple[str, ...]
    log_level: str

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "DesktopRelayHostConfig":
        mode = RelayRuntimeMode.parse(str(payload.get("mode") or "host"))
        return cls(
            mode=mode,
            authority_url=_clean_optional(payload.get("authority_url")),
            access_token=_clean_optional(payload.get("access_token")),
            client_version=str(payload.get("client_version") or "0.1.0"),
            heartbeat_interval_seconds=int(payload.get("heartbeat_interval_seconds") or 30),
            reconnect_delay_seconds=int(payload.get("reconnect_delay_seconds") or 5),
            bind_host=str(payload.get("bind_host") or "127.0.0.1"),
            bind_port=int(payload.get("bind_port") or 8082),
            display_name=str(payload.get("display_name") or platform.node() or "Desktop Host"),
            device_id=str(payload.get("device_id") or platform.node() or "desktop-host"),
            relay_server_id=str(payload.get("relay_server_id") or "desktop-host"),
            allowed_roots=_normalize_paths(payload.get("allowed_roots"), fallback=["."]),
            service_definitions_dir=Path(
                str(payload.get("service_definitions_dir") or "./service-definitions")
            ).expanduser().resolve(),
            enabled_personas=_normalize_personas(payload.get("enabled_personas")),
            log_level=str(payload.get("log_level") or "INFO").upper(),
        )

    @classmethod
    def from_env(cls) -> "DesktopRelayHostConfig":
        return cls.from_mapping(
            {
                "mode": os.getenv("AGIENCE_RELAY_MODE", "host"),
                "authority_url": os.getenv("AGIENCE_AUTHORITY_URL"),
                "access_token": os.getenv("AGIENCE_RELAY_ACCESS_TOKEN"),
                "client_version": os.getenv("AGIENCE_RELAY_CLIENT_VERSION", "0.1.0"),
                "heartbeat_interval_seconds": os.getenv("AGIENCE_RELAY_HEARTBEAT_INTERVAL", "30"),
                "reconnect_delay_seconds": os.getenv("AGIENCE_RELAY_RECONNECT_DELAY", "5"),
                "bind_host": os.getenv("AGIENCE_RELAY_BIND_HOST", "127.0.0.1"),
                "bind_port": os.getenv("AGIENCE_RELAY_BIND_PORT", "8082"),
                "display_name": os.getenv("AGIENCE_RELAY_DISPLAY_NAME") or platform.node() or "Desktop Host",
                "device_id": os.getenv("AGIENCE_RELAY_DEVICE_ID") or platform.node() or "desktop-host",
                "relay_server_id": os.getenv("AGIENCE_RELAY_SERVER_ID", "desktop-host"),
                "allowed_roots": _split_csv(os.getenv("AGIENCE_RELAY_ALLOWED_ROOTS")) or (".",),
                "service_definitions_dir": os.getenv(
                    "AGIENCE_RELAY_SERVICE_DEFINITIONS_DIR", "./service-definitions"
                ),
                "enabled_personas": _split_csv(os.getenv("AGIENCE_RELAY_ENABLED_PERSONAS")),
                "log_level": os.getenv("AGIENCE_RELAY_LOG_LEVEL", "INFO"),
            }
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "DesktopRelayHostConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Desktop relay config file must contain a JSON object.")
        return cls.from_mapping(payload)


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None