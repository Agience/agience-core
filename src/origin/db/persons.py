"""Postgres CRUD for `persons` — replaces Arango `people` lookups.

Returns the SQLAlchemy `Person` model directly. Callers convert to the existing
`entities.person.Person` entity (or a Pydantic shape) at the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from origin.models.person import Person


def get_by_id(db: Session, person_id: str) -> Optional[Person]:
    return db.get(Person, _to_uuid(person_id))


def get_by_email(db: Session, email: str) -> Optional[Person]:
    return db.execute(
        select(Person).where(Person.email == email.strip()).limit(1)
    ).scalar_one_or_none()


def get_by_username(db: Session, username: str) -> Optional[Person]:
    return db.execute(
        select(Person).where(Person.username == username.strip()).limit(1)
    ).scalar_one_or_none()


def get_by_oidc_identity(
    db: Session, oidc_provider: str, oidc_subject: str
) -> Optional[Person]:
    return db.execute(
        select(Person)
        .where(Person.oidc_provider == oidc_provider, Person.oidc_subject == oidc_subject)
        .limit(1)
    ).scalar_one_or_none()


def get_by_google_id(db: Session, google_id: str) -> Optional[Person]:
    found = get_by_oidc_identity(db, "google", google_id)
    if found:
        return found
    return db.execute(
        select(Person).where(Person.google_id == google_id).limit(1)
    ).scalar_one_or_none()


def create(db: Session, fields: Mapping[str, Any]) -> Person:
    """Insert a new Person. `id` may be supplied; otherwise generated."""
    payload = dict(fields)
    if "id" in payload and payload["id"]:
        payload["id"] = _to_uuid(payload["id"])
    else:
        payload["id"] = uuid.uuid4()
    payload.setdefault("preferences", {})
    person = Person(**payload)
    db.add(person)
    db.flush()
    return person


def update(db: Session, person_id: str, fields: Mapping[str, Any]) -> Person:
    person = db.get(Person, _to_uuid(person_id))
    if person is None:
        raise LookupError(f"Person {person_id} not found")
    for key, value in fields.items():
        setattr(person, key, value)
    person.modified_time = datetime.now(timezone.utc)
    db.flush()
    return person


def update_preferences(db: Session, person_id: str, preferences: dict) -> Person:
    return update(db, person_id, {"preferences": preferences or {}})


def count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Person)).scalar_one()


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
