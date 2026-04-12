"""In-process event bus for artifact lifecycle and operation events.

Single API: `Event` + `EventFilter` dataclasses, `publish_event` (async),
`publish_event_sync` (thread-safe), `subscribe_filtered`,
`unsubscribe_filtered`, and a convenience helper `emit_artifact_event_sync`
for the common `{artifact: dict}` payload used by service-layer code.

For multi-replica deployments, replace `_filtered_subscribers` with a Redis
pub/sub adapter; routers and services stay the same.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified event model
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """A single event broadcast through the bus.

    `name` is the dotted event identifier (e.g. `artifact.created`,
    `artifact.invoke.completed`). `payload` is the free-form JSON body. The
    other fields are used for server-side filter evaluation.
    """

    name: str
    payload: Dict[str, Any]
    container_id: Optional[str] = None
    artifact_id: Optional[str] = None
    content_type: Optional[str] = None
    actor_id: Optional[str] = None
    ts: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class EventFilter:
    """Server-side filter applied to events before they reach a subscriber.

    An event matches if every provided field matches. Empty fields match
    anything. `event_names` supports fnmatch globs (e.g. `artifact.invoke.*`).
    """

    container_id: Optional[str] = None
    artifact_id: Optional[str] = None
    content_type: Optional[str] = None
    event_names: Optional[List[str]] = None

    def matches(self, event: Event) -> bool:
        if self.container_id and self.container_id != event.container_id:
            return False
        if self.artifact_id and self.artifact_id != event.artifact_id:
            return False
        if self.content_type and self.content_type != event.content_type:
            return False
        if self.event_names:
            if not any(fnmatch.fnmatchcase(event.name, pat) for pat in self.event_names):
                return False
        return True


@dataclass
class _FilteredSubscription:
    filter: EventFilter
    queue: "asyncio.Queue[Event]"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

# All active filtered subscriptions (global list; filter evaluated per event)
_filtered_subscribers: list[_FilteredSubscription] = []

_loop: Optional[asyncio.AbstractEventLoop] = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store the running event loop so sync callers can schedule coroutines."""
    global _loop
    _loop = loop


# ---------------------------------------------------------------------------
# Subscription API
# ---------------------------------------------------------------------------

async def subscribe_filtered(event_filter: EventFilter) -> "asyncio.Queue[Event]":
    """Register a filtered subscriber. Returns a queue of `Event` objects."""
    q: "asyncio.Queue[Event]" = asyncio.Queue()
    _filtered_subscribers.append(_FilteredSubscription(filter=event_filter, queue=q))
    return q


async def unsubscribe_filtered(q: "asyncio.Queue[Event]") -> None:
    """Remove a filtered subscriber by its queue. Safe if already removed."""
    global _filtered_subscribers
    _filtered_subscribers = [s for s in _filtered_subscribers if s.queue is not q]


# ---------------------------------------------------------------------------
# Publish API
# ---------------------------------------------------------------------------

async def publish_event(event: Event) -> None:
    """Publish a unified `Event` to every matching filtered subscriber."""
    await _fanout_filtered(event)


def publish_event_sync(event: Event) -> None:
    """Thread-safe `publish_event` for synchronous callers. Schedules the
    coroutine on the stored event loop; no-op if the loop is not yet
    available (early bootstrap)."""
    if _loop is None or _loop.is_closed():
        return
    asyncio.run_coroutine_threadsafe(publish_event(event), _loop)


def _extract_artifact_fields(data: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Best-effort extraction of (artifact_id, content_type) from a service-layer
    payload of shape `{artifact: {...}}` or `{artifact_id: "..."}`."""
    artifact_obj = data.get("artifact")
    artifact_id: Optional[str] = None
    content_type: Optional[str] = None
    if isinstance(artifact_obj, dict):
        artifact_id = artifact_obj.get("id") or artifact_obj.get("_key")
        ctx = artifact_obj.get("context")
        if isinstance(ctx, str):
            import json
            try:
                ctx = json.loads(ctx)
            except Exception:
                ctx = None
        if isinstance(ctx, dict):
            content_type = ctx.get("content_type")
    if artifact_id is None:
        artifact_id = data.get("artifact_id")
    return artifact_id, content_type


def emit_artifact_event_sync(
    container_id: str,
    event_name: str,
    data: Dict[str, Any],
    *,
    actor_id: Optional[str] = None,
) -> None:
    """Convenience helper for service-layer code that previously called
    `publish_sync(workspace_id, event_type, {"artifact": ...})`. Constructs
    an `Event` with extracted artifact_id / content_type and publishes it through the
    thread-safe path.
    """
    artifact_id, content_type = _extract_artifact_fields(data)
    event = Event(
        name=event_name,
        payload=data,
        container_id=container_id,
        artifact_id=artifact_id,
        content_type=content_type,
        actor_id=actor_id,
    )
    publish_event_sync(event)


async def _fanout_filtered(event: Event) -> None:
    """Deliver an event to every matching filtered subscriber."""
    subs = list(_filtered_subscribers)
    for sub in subs:
        if not sub.filter.matches(event):
            continue
        try:
            await sub.queue.put(event)
        except Exception as exc:
            logger.warning("Filtered event bus put failed for event %s: %s", event.name, exc)
