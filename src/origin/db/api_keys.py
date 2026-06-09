"""Postgres CRUD for `api_keys`."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import select, update as sa_update
from sqlalchemy.orm import Session

from origin.models.api_key import ApiKey


def get_by_hash(db: Session, key_hash: str) -> Optional[ApiKey]:
    return db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash).limit(1)
    ).scalar_one_or_none()


def get_by_id(db: Session, api_key_id: str) -> Optional[ApiKey]:
    return db.get(ApiKey, _to_uuid(api_key_id))


def get_by_user(db: Session, user_id: str) -> list[ApiKey]:
    return list(
        db.execute(
            select(ApiKey)
            .where(ApiKey.user_id == _to_uuid(user_id))
            .order_by(ApiKey.created_time.desc())
        ).scalars()
    )


def create(db: Session, fields: Mapping[str, Any]) -> ApiKey:
    payload = dict(fields)
    if "id" in payload and payload["id"]:
        payload["id"] = _to_uuid(payload["id"])
    else:
        payload["id"] = uuid.uuid4()
    if "user_id" in payload and payload["user_id"]:
        payload["user_id"] = _to_uuid(payload["user_id"])
    for uuid_field in ("host_id", "server_id", "agent_id", "issued_by_user_id"):
        if uuid_field in payload and payload[uuid_field]:
            payload[uuid_field] = _to_uuid(payload[uuid_field])
    api_key = ApiKey(**payload)
    db.add(api_key)
    db.flush()
    return api_key


def update(db: Session, api_key_id: str, fields: Mapping[str, Any]) -> Optional[ApiKey]:
    api_key = db.get(ApiKey, _to_uuid(api_key_id))
    if api_key is None:
        return None
    for uuid_field in ("host_id", "server_id", "agent_id"):
        if uuid_field in fields and fields[uuid_field]:
            fields = {**fields, uuid_field: _to_uuid(fields[uuid_field])}
    for key, value in fields.items():
        setattr(api_key, key, value)
    api_key.modified_time = datetime.now(timezone.utc)
    db.flush()
    return api_key


def update_last_used(db: Session, api_key_id: str | uuid.UUID, when: Optional[datetime] = None) -> None:
    db.execute(
        sa_update(ApiKey)
        .where(ApiKey.id == _to_uuid(api_key_id))
        .values(last_used_at=when or datetime.now(timezone.utc))
    )


def delete(db: Session, api_key_id: str) -> bool:
    api_key = db.get(ApiKey, _to_uuid(api_key_id))
    if api_key is None:
        return False
    db.delete(api_key)
    db.flush()
    return True


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
