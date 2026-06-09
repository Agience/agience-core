from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from .config import DesktopRelayHostConfig
from .relay_protocol import RelayEnvelope
from .relay_runtime import RelayRuntimeHandler
from .relay_state import RelayState


class RelayClient:
    def __init__(self, config: DesktopRelayHostConfig, runtime: RelayRuntimeHandler, state: RelayState):
        self.config = config
        self.runtime = runtime
        self.state = state

    @property
    def enabled(self) -> bool:
        return bool(self.config.authority_url and self.config.access_token)

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        if not self.enabled:
            return

        while not stop_event.is_set():
            try:
                await self._run_once(stop_event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.state.mark_disconnected(str(exc))
            if not stop_event.is_set():
                await asyncio.sleep(self.config.reconnect_delay_seconds)

    async def _run_once(self, stop_event: asyncio.Event) -> None:
        connect = _load_websocket_connect()
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "X-Device-Id": self.config.device_id,
            "X-Agience-Client": f"desktop-host/{self.config.client_version}",
        }
        async with connect(self._relay_url(), additional_headers=headers) as websocket:
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(websocket, stop_event))
            try:
                async for raw_message in websocket:
                    self.state.mark_message()
                    payload = json.loads(raw_message)
                    envelope = RelayEnvelope.from_dict(payload)
                    responses = await self._handle_incoming(envelope)
                    for response in responses:
                        await websocket.send(json.dumps(response.to_dict()))
            finally:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
                self.state.mark_disconnected()

    async def _handle_incoming(self, envelope: RelayEnvelope) -> list[RelayEnvelope]:
        if envelope.type == "server_hello":
            session_id = str(envelope.payload.get("session_id")) if envelope.payload.get("session_id") else None
            self.state.mark_connected(session_id=session_id)
            return [self.runtime.build_client_hello()]
        return self.runtime.handle_message(envelope)

    async def _heartbeat_loop(self, websocket: Any, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await asyncio.sleep(self.config.heartbeat_interval_seconds)
            await websocket.send(json.dumps(RelayEnvelope(type="ping", payload={}).to_dict()))

    def _relay_url(self) -> str:
        assert self.config.authority_url is not None
        base = self.config.authority_url.rstrip("/")
        if base.startswith("https://"):
            base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            base = "ws://" + base[len("http://"):]
        elif not base.startswith(("ws://", "wss://")):
            base = "wss://" + base
        return f"{base}/relay/v1/connect"


def _load_websocket_connect():
    from websockets.asyncio.client import connect  # type: ignore[import-not-found]

    return connect