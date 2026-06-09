"""Origin person service — Postgres-backed.

This is intentionally simpler than Mantle's `services/person_service.py`. It
does NOT auto-provision a workspace/inbox or seed platform collections — those
live in Mantle. Origin owns identity only. Workspace/inbox creation happens
lazily in Mantle on first authenticated access (or via the manifest in 1.1e).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from kernel import config
from origin.db import persons as db_persons
from origin.models.person import Person
from origin.services.auth_service import is_person_allowed

logger = logging.getLogger(__name__)


async def record_person_event(payload: dict, event_type: str = "person") -> None:
    """Fire-and-forget POST to the configured external event webhook.

    No-op when the webhook isn't configured. Mirrors Mantle's behavior so
    auth event emission survives the move unchanged.
    """
    uri = getattr(config, "EVENT_LOGGER_URI", None)
    user = getattr(config, "EVENT_LOGGER_USERNAME", None)
    password = getattr(config, "EVENT_LOGGER_PASSWORD", None)
    if not uri or not user or not password:
        return
    try:
        body = {**payload, "event_type": event_type}
        async with httpx.AsyncClient(
            timeout=2.0, auth=httpx.BasicAuth(username=user, password=password)
        ) as client:
            await client.post(uri, json=body)
    except Exception:
        logger.exception("Failed to record person event")


def get_user_by_id(db: Session, user_id: str) -> Optional[Person]:
    return db_persons.get_by_id(db, user_id)


def get_user_by_email(db: Session, email: str) -> Optional[Person]:
    return db_persons.get_by_email(db, email)


def get_user_by_username(db: Session, username: str) -> Optional[Person]:
    return db_persons.get_by_username(db, username)


def get_user_by_oidc_identity(
    db: Session, oidc_provider: str, oidc_subject: str
) -> Optional[Person]:
    return db_persons.get_by_oidc_identity(db, oidc_provider, oidc_subject)


def get_user_by_google_id(db: Session, google_id: str) -> Optional[Person]:
    return db_persons.get_by_google_id(db, google_id)


def get_or_create_user_by_oidc_identity(
    db: Session,
    oidc_provider: str,
    oidc_subject: str,
    email: str,
    name: str,
    picture: Optional[str] = None,
) -> Person:
    email = (email or "").strip().lower()
    name = (name or "").strip() or "User"
    google_id = oidc_subject if oidc_provider == "google" else None
    if not is_person_allowed(google_id, email):
        logger.warning("Login denied: provider=%r subject=%r email=%r", oidc_provider, oidc_subject, email)
        raise PermissionError("Person is not allowed to access this system")

    existing = get_user_by_oidc_identity(db, oidc_provider, oidc_subject)
    if existing:
        dirty = False
        if existing.email != email:
            existing.email = email
            dirty = True
        if existing.name != name:
            existing.name = name
            dirty = True
        if existing.picture != picture:
            existing.picture = picture
            dirty = True
        if dirty:
            existing.oidc_provider = oidc_provider
            existing.oidc_subject = oidc_subject
            db.flush()
        return existing

    return db_persons.create(
        db,
        {
            "google_id": oidc_subject if oidc_provider == "google" else None,
            "oidc_provider": oidc_provider,
            "oidc_subject": oidc_subject,
            "email": email,
            "name": name,
            "picture": picture,
        },
    )


def create_user_with_password(
    db: Session,
    *,
    username: str,
    name: str,
    password_hash: str,
    email: str = "",
) -> Person:
    username = (username or "").strip()
    email = (email or "").strip().lower()
    name = (name or username).strip() or "User"

    if not username:
        raise ValueError("Username is required")
    if email and not is_person_allowed(None, email):
        raise PermissionError("Person is not allowed to access this system")

    if get_user_by_username(db, username):
        raise ValueError("Username already taken")
    if email and get_user_by_email(db, email):
        raise ValueError("Email already registered")

    return db_persons.create(
        db,
        {
            "username": username,
            "email": email or None,
            "name": name,
            "password_hash": password_hash,
        },
    )


def get_or_create_user_by_email(db: Session, email: str) -> Person:
    """Used for email-OTP login. Creates a passwordless user if missing."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Valid email is required")
    if not is_person_allowed(None, email):
        raise PermissionError("Person is not allowed to access this system")

    existing = get_user_by_email(db, email)
    if existing:
        return existing

    return db_persons.create(
        db,
        {"email": email, "name": email.split("@")[0]},
    )


def link_oidc_identity(
    db: Session, *, user_id: str, oidc_provider: str, oidc_subject: str
) -> Person:
    existing = get_user_by_oidc_identity(db, oidc_provider, oidc_subject)
    if existing:
        if str(existing.id) == str(user_id):
            return existing
        raise ValueError("This identity is already linked to another account")

    user = get_user_by_id(db, user_id)
    if user is None:
        raise ValueError("User not found")
    if user.oidc_provider and user.oidc_subject:
        raise ValueError(f"Account already linked to {user.oidc_provider}. Unlink first.")

    user.oidc_provider = oidc_provider
    user.oidc_subject = oidc_subject
    if oidc_provider == "google":
        user.google_id = oidc_subject
    db.flush()
    return user


def unlink_oidc_identity(db: Session, user_id: str) -> Person:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise ValueError("User not found")
    if not user.password_hash:
        raise ValueError("Cannot unlink: no password is set on this account")
    if not user.oidc_provider:
        raise ValueError("No linked identity to remove")
    user.oidc_provider = None
    user.oidc_subject = None
    db.flush()
    return user


def update_preferences(db: Session, user_id: str, preferences: dict) -> Person:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise ValueError(f"Person {user_id} not found")
    merged = dict(user.preferences or {})
    merged.update(preferences or {})
    user.preferences = merged
    db.flush()
    return user
