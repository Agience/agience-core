"""Postgres CRUD for `passkey_credentials`.

WebAuthn `credential_id` is variable-length base64url (kept as String PK).
Functions match the surface of the Arango-backed `arango_identity` module:
get-by-id, list-for-person, create, update, delete.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from origin.models.passkey_credential import PasskeyCredential


def get_by_id(db: Session, credential_id: str) -> Optional[PasskeyCredential]:
    return db.get(PasskeyCredential, credential_id)


def get_by_id_and_person(
    db: Session, credential_id: str, person_id: str
) -> Optional[PasskeyCredential]:
    return db.execute(
        select(PasskeyCredential)
        .where(
            PasskeyCredential.id == credential_id,
            PasskeyCredential.person_id == _to_uuid(person_id),
        )
        .limit(1)
    ).scalar_one_or_none()


def list_for_person(db: Session, person_id: str) -> list[PasskeyCredential]:
    return list(
        db.execute(
            select(PasskeyCredential).where(
                PasskeyCredential.person_id == _to_uuid(person_id)
            )
        ).scalars()
    )


def create(db: Session, fields: Mapping[str, Any]) -> PasskeyCredential:
    payload = dict(fields)
    if "person_id" in payload and payload["person_id"]:
        payload["person_id"] = _to_uuid(payload["person_id"])
    cred = PasskeyCredential(**payload)
    db.add(cred)
    db.flush()
    return cred


def update_sign_count(db: Session, credential_id: str, sign_count: int) -> None:
    cred = db.get(PasskeyCredential, credential_id)
    if cred is None:
        return
    cred.sign_count = sign_count
    cred.last_used_at = datetime.now(timezone.utc)
    db.flush()


def delete_for_person(db: Session, credential_id: str, person_id: str) -> bool:
    cred = get_by_id_and_person(db, credential_id, person_id)
    if cred is None:
        return False
    db.delete(cred)
    db.flush()
    return True


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
