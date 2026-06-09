"""Postgres CRUD for `server_credentials`."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import select, update as sa_update
from sqlalchemy.orm import Session

from origin.models.server_credential import ServerCredential


def get_by_client_id(db: Session, client_id: str) -> Optional[ServerCredential]:
    return db.execute(
        select(ServerCredential).where(ServerCredential.client_id == client_id).limit(1)
    ).scalar_one_or_none()


def get_by_id(db: Session, credential_id: str) -> Optional[ServerCredential]:
    return db.get(ServerCredential, _to_uuid(credential_id))


def list_all(db: Session) -> list[ServerCredential]:
    return list(
        db.execute(select(ServerCredential).order_by(ServerCredential.created_time.desc())).scalars()
    )


def create(db: Session, fields: Mapping[str, Any]) -> ServerCredential:
    payload = dict(fields)
    if "id" in payload and payload["id"]:
        payload["id"] = _to_uuid(payload["id"])
    else:
        payload["id"] = uuid.uuid4()
    for uuid_field in ("host_id", "server_id", "user_id"):
        if uuid_field in payload and payload[uuid_field]:
            payload[uuid_field] = _to_uuid(payload[uuid_field])
    cred = ServerCredential(**payload)
    db.add(cred)
    db.flush()
    return cred


def update(db: Session, credential_id: str, fields: Mapping[str, Any]) -> Optional[ServerCredential]:
    cred = db.get(ServerCredential, _to_uuid(credential_id))
    if cred is None:
        return None
    for key, value in fields.items():
        setattr(cred, key, value)
    cred.modified_time = datetime.now(timezone.utc)
    db.flush()
    return cred


def update_last_used(
    db: Session, credential_id: str | uuid.UUID, when: Optional[datetime] = None
) -> None:
    db.execute(
        sa_update(ServerCredential)
        .where(ServerCredential.id == _to_uuid(credential_id))
        .values(last_used_at=when or datetime.now(timezone.utc))
    )


def rotate_secret(
    db: Session, credential_id: str, new_secret_hash: str
) -> Optional[ServerCredential]:
    cred = db.get(ServerCredential, _to_uuid(credential_id))
    if cred is None:
        return None
    now = datetime.now(timezone.utc)
    cred.secret_hash = new_secret_hash
    cred.last_rotated_at = now
    cred.modified_time = now
    db.flush()
    return cred


def delete(db: Session, credential_id: str) -> bool:
    cred = db.get(ServerCredential, _to_uuid(credential_id))
    if cred is None:
        return False
    db.delete(cred)
    db.flush()
    return True


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
