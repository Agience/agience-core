from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class RelayStatusSnapshot:
    configured: bool
    connected: bool
    authority_url: str | None
    session_id: str | None
    last_error: str | None
    last_message_at: str | None


class RelayState:
    def __init__(self, authority_url: str | None, configured: bool):
        self._lock = Lock()
        self._authority_url = authority_url
        self._configured = configured
        self._connected = False
        self._session_id: str | None = None
        self._last_error: str | None = None
        self._last_message_at: str | None = None

    def mark_connected(self, session_id: str | None = None) -> None:
        with self._lock:
            self._connected = True
            self._session_id = session_id or self._session_id
            self._last_error = None
            self._touch_locked()

    def mark_disconnected(self, error: str | None = None) -> None:
        with self._lock:
            self._connected = False
            if error:
                self._last_error = error

    def mark_message(self) -> None:
        with self._lock:
            self._touch_locked()

    def snapshot(self) -> RelayStatusSnapshot:
        with self._lock:
            return RelayStatusSnapshot(
                configured=self._configured,
                connected=self._connected,
                authority_url=self._authority_url,
                session_id=self._session_id,
                last_error=self._last_error,
                last_message_at=self._last_message_at,
            )

    def as_dict(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "configured": snapshot.configured,
            "connected": snapshot.connected,
            "authority_url": snapshot.authority_url,
            "session_id": snapshot.session_id,
            "last_error": snapshot.last_error,
            "last_message_at": snapshot.last_message_at,
        }

    def _touch_locked(self) -> None:
        self._last_message_at = datetime.now(timezone.utc).isoformat()