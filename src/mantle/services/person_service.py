"""Mantle-side person service — thin HTTP shim to Origin.

After 1.1e, Person records live in Origin's Postgres. Mantle only needs
`get_user_by_id` (used by `services.dependencies.get_person`) and the
fire-and-forget `record_person_event` webhook (used historically by auth
flows that have since moved to Origin — kept as a no-op for back-compat
imports).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from clients.origin_client import get_origin_client
from entities.person import Person as PersonEntity

logger = logging.getLogger(__name__)


def get_user_by_id(db, id: str) -> Optional[PersonEntity]:  # noqa: A002 — keep `id` for compat
    """Resolve a Person by ID via Origin's `/internal/persons/{id}` endpoint.

    `db` is unused — Origin owns identity. Kept for signature compatibility
    with the historical Arango-backed function.
    """
    del db
    if not id:
        return None
    client = get_origin_client()
    try:
        resp = client._client.get(  # noqa: SLF001
            f"{client._base}/internal/persons/{id}",
            headers={"Authorization": f"Bearer {client._service_token()}"},  # noqa: SLF001
        )
    except httpx.HTTPError:
        logger.warning("Origin unreachable in get_user_by_id(%s)", id, exc_info=True)
        return None
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        logger.warning("Origin /internal/persons/%s returned %d", id, resp.status_code)
        return None
    try:
        return PersonEntity.from_dict(resp.json() or {})
    except (ValueError, KeyError):
        return None


async def record_person_event(payload: dict, event_type: str = "person") -> None:
    """No-op shim. Origin owns the event-logging webhook now.

    Kept so imports from legacy modules don't break; emission has already
    moved to Origin's `auth_service.record_person_event`.
    """
    del payload, event_type
    return None
