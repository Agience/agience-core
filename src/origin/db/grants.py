"""Postgres CRUD for `grants`.

Read functions used by `resolve_auth`, `check_access`, and the
grants_router. Writes covered: create, update (revoke/accept/claims_count
mutation), delete.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from origin.models.grant import Grant


def get_by_id(db: Session, grant_id: str) -> Optional[Grant]:
    return db.get(Grant, _to_uuid(grant_id))


def list_for_resource(db: Session, resource_id: str) -> list[Grant]:
    return list(
        db.execute(
            select(Grant)
            .where(Grant.resource_id == _to_uuid(resource_id))
            .order_by(Grant.created_time.asc())
        ).scalars()
    )


def get_active_for_principal_resource(
    db: Session, *, grantee_id: str, resource_id: str | uuid.UUID
) -> list[Grant]:
    return list(
        db.execute(
            select(Grant).where(
                Grant.grantee_id == grantee_id,
                Grant.resource_id == _to_uuid(resource_id),
                Grant.state == "active",
            )
        ).scalars()
    )


def get_active_for_grantee(
    db: Session, grantee_id: str, grantee_type: str = "user"
) -> list[Grant]:
    return list(
        db.execute(
            select(Grant).where(
                Grant.grantee_id == grantee_id,
                Grant.grantee_type == grantee_type,
                Grant.state == "active",
            )
        ).scalars()
    )


def get_active_by_key(db: Session, raw_key: str) -> list[Grant]:
    """Resolve a Bearer-presented grant key to its active grant.

    Hash matches `grant_service`'s storage format — SHA-256 hex of the raw
    presentation token.
    """
    if not raw_key:
        return []
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return list(
        db.execute(
            select(Grant).where(
                Grant.grantee_type == "invite",
                Grant.grantee_id == digest,
                Grant.state == "active",
            )
        ).scalars()
    )


def list_invites_sent(
    db: Session, granted_by: str, *, include_revoked: bool = False
) -> list[Grant]:
    stmt = select(Grant).where(
        Grant.grantee_type == "invite",
        Grant.granted_by == _to_uuid(granted_by),
    )
    if not include_revoked:
        stmt = stmt.where(Grant.state == "active")
    return list(db.execute(stmt.order_by(Grant.created_time.desc())).scalars())


def find_existing_user_grant(
    db: Session, *, user_id: str, resource_id: str
) -> Optional[Grant]:
    """Used by the upsert path: find a single user→resource grant if any."""
    return db.execute(
        select(Grant)
        .where(
            Grant.grantee_type == "user",
            Grant.grantee_id == user_id,
            Grant.resource_id == _to_uuid(resource_id),
            or_(Grant.state == "active", Grant.state == "pending_accept"),
        )
        .limit(1)
    ).scalar_one_or_none()


def create(db: Session, fields: Mapping[str, Any]) -> Grant:
    payload = dict(fields)
    if "id" in payload and payload["id"]:
        payload["id"] = _to_uuid(payload["id"])
    else:
        payload["id"] = uuid.uuid4()
    if "resource_id" in payload and payload["resource_id"]:
        payload["resource_id"] = _to_uuid(payload["resource_id"])
    for uuid_field in ("granted_by", "accepted_by", "revoked_by"):
        if uuid_field in payload and payload[uuid_field]:
            payload[uuid_field] = _to_uuid(payload[uuid_field])
    grant = Grant(**payload)
    db.add(grant)
    db.flush()
    return grant


def update_grant(db: Session, grant_id: str, fields: Mapping[str, Any]) -> Optional[Grant]:
    grant = db.get(Grant, _to_uuid(grant_id))
    if grant is None:
        return None
    for uuid_field in ("accepted_by", "revoked_by"):
        if uuid_field in fields and fields[uuid_field]:
            fields = {**fields, uuid_field: _to_uuid(fields[uuid_field])}
    for key, value in fields.items():
        setattr(grant, key, value)
    grant.modified_time = datetime.now(timezone.utc)
    db.flush()
    return grant


def delete(db: Session, grant_id: str) -> bool:
    grant = db.get(Grant, _to_uuid(grant_id))
    if grant is None:
        return False
    db.delete(grant)
    db.flush()
    return True


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


__all__: Iterable[str] = (
    "get_by_id",
    "list_for_resource",
    "get_active_for_principal_resource",
    "get_active_for_grantee",
    "get_active_by_key",
    "list_invites_sent",
    "find_existing_user_grant",
    "create",
    "update_grant",
    "delete",
)
