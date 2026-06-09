from __future__ import annotations

from enum import Enum


class RelayRuntimeMode(str, Enum):
    HOST = "host"
    AUTHORITY = "authority"

    @classmethod
    def parse(cls, value: str | None) -> "RelayRuntimeMode":
        normalized = (value or cls.HOST.value).strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            allowed = ", ".join(mode.value for mode in cls)
            raise ValueError(f"Unknown relay runtime mode '{value}'. Expected one of: {allowed}.") from exc