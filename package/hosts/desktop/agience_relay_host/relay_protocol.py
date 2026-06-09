from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class RelayEnvelope:
    type: str
    payload: dict[str, Any]
    v: int = 1
    id: str | None = None
    ts: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "v": self.v,
            "id": self.id or str(uuid4()),
            "ts": self.ts if self.ts is not None else int(time()),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RelayEnvelope":
        return cls(
            type=str(payload["type"]),
            payload=dict(payload.get("payload") or {}),
            v=int(payload.get("v") or 1),
            id=str(payload.get("id")) if payload.get("id") is not None else None,
            ts=int(payload["ts"]) if payload.get("ts") is not None else None,
        )


def relay_error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details or {},
    }