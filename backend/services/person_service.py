# services/person_service.py

import logging
from typing import Dict, Optional
import httpx
from arango.database import StandardDatabase

from services.auth_service import is_person_allowed
from entities.person import Person as PersonEntity
from db import arango_identity as arango_ws
from core.config import AGIENCE_PLATFORM_USER_ID
from core import config

logger = logging.getLogger(__name__)

async def record_person_event(payload: dict, event_type: str = 'person') -> None:
    """
    Fire-and-forget POST to your event webhook.
    Expects payload to include dictionary with event details.
    """
    if not config.EVENT_LOGGER_URI or not config.EVENT_LOGGER_USERNAME or not config.EVENT_LOGGER_PASSWORD:
        logger.debug("Event logger not configured, skipping person event log")
        return

    try:
        body = {**payload, "event_type": event_type}
        async with httpx.AsyncClient(
            timeout=2.0,
            auth=httpx.BasicAuth(username=config.EVENT_LOGGER_USERNAME, password=config.EVENT_LOGGER_PASSWORD),
        ) as client:
            await client.post(config.EVENT_LOGGER_URI, json=body)
    except Exception:
        logger.exception("Failed to record token event")

def create_person(db: StandardDatabase, entity: PersonEntity) -> PersonEntity:
    person_dict = entity.to_dict()
    # Include password_hash which to_dict() omits (it only exposes has_password)
    if entity.password_hash:
        person_dict["password_hash"] = entity.password_hash
    new_id = arango_ws.create_person(db, person_dict)
    if not new_id:
        raise RuntimeError(f"Failed to create person {entity.email}")
    entity.id = new_id
    return entity

def update_person(db: StandardDatabase, entity: PersonEntity) -> PersonEntity:
    updates = {
        "google_id": entity.google_id,
        "oidc_provider": entity.oidc_provider,
        "oidc_subject": entity.oidc_subject,
        "email": entity.email,
        "name": entity.name,
        "picture": entity.picture,
        "preferences": entity.preferences,
    }
    if entity.password_hash is not None:
        updates["password_hash"] = entity.password_hash
    ok = arango_ws.update_person(db, str(entity.id), updates)
    if not ok:
        raise RuntimeError(f"Failed to update person {entity.id}")
    return entity

def get_user_by_id(db: StandardDatabase, id: str) -> PersonEntity | None:
    """
    Retrieve a user by ID. returns None if not found.
    """
    doc = arango_ws.get_person_by_id(db, id)
    if not doc:
        return None
    return PersonEntity.from_dict(doc)

def get_user_by_google_id(db: StandardDatabase, google_id: str) -> PersonEntity | None:
    """
    Retrieve a user by Google ID. returns None if not found.
    """
    doc = arango_ws.get_person_by_google_id(db, google_id)
    if not doc:
        return None
    return PersonEntity.from_dict(doc)


def get_user_by_oidc_identity(db: StandardDatabase, oidc_provider: str, oidc_subject: str) -> PersonEntity | None:
    doc = arango_ws.get_person_by_oidc_identity(db, oidc_provider, oidc_subject)
    if not doc:
        return None
    return PersonEntity.from_dict(doc)


def get_user_by_email(db: StandardDatabase, email: str) -> PersonEntity | None:
    doc = arango_ws.get_person_by_email(db, email)
    if not doc:
        return None
    return PersonEntity.from_dict(doc)


def get_user_by_username(db: StandardDatabase, username: str) -> PersonEntity | None:
    doc = arango_ws.get_person_by_username(db, username)
    if not doc:
        return None
    return PersonEntity.from_dict(doc)


def _provision_new_user_defaults(arango_db: StandardDatabase, new_person: PersonEntity) -> None:
    # In the unified model the user's home collection IS their workspace —
    # a single collection with content_type=workspace and id=user_id that
    # holds both drafts and committed artifacts.
    from services.workspace_service import create_workspace

    create_workspace(
        db=arango_db,
        user_id=new_person.id,
        name="Inbox",
        is_inbox=True,
        arango_db=arango_db,
    )

    # Seed first-login content and grant access to platform-owned collections.
    try:
        from services.seed_content_service import apply_platform_collections_to_user

        apply_platform_collections_to_user(arango_db, new_person.id)
    except Exception:
        logger.exception("Failed to seed first-login content for user %s", new_person.id)

    # First-user auto-promotion: if this is the only user, grant admin (write)
    # on all platform collections. The person was already inserted before this
    # function is called, so count == 1 means "I'm the first user."
    try:
        person_count = arango_ws.count_people(arango_db)
        if person_count == 1:
            from services.platform_topology import get_all_platform_collection_ids
            from db.arango import upsert_user_collection_grant as db_upsert_grant

            for col_id in get_all_platform_collection_ids():
                db_upsert_grant(
                    arango_db,
                    user_id=new_person.id,
                    collection_id=col_id,
                    granted_by=AGIENCE_PLATFORM_USER_ID,
                    can_read=True,
                    can_update=True,
                    name="Platform admin (first user auto-grant)",
                )
            logger.info("First user %s auto-promoted to platform admin", new_person.id)
    except Exception:
        logger.exception("Failed first-user admin auto-promotion for user %s", new_person.id)


def get_or_create_user_by_oidc_identity(
    db: StandardDatabase,
    oidc_provider: str,
    oidc_subject: str,
    email: str,
    name: str,
    picture: Optional[str] = None,
) -> PersonEntity:
    """Get or create a user based on OIDC provider + subject."""
    email = (email or "").strip().lower()
    name = (name or "").strip() or "User"
    google_id = oidc_subject if oidc_provider == "google" else None
    if not is_person_allowed(google_id, email):
        logger.warning("Login denied: provider=%r subject=%r email=%r", oidc_provider, oidc_subject, email)
        raise PermissionError("Person is not allowed to access this system")

    existing = get_user_by_oidc_identity(db, oidc_provider, oidc_subject)
    if existing:
        updated = False
        if existing.email != email:
            existing.email = email
            updated = True
        if existing.name != name:
            existing.name = name
            updated = True
        if existing.picture != picture:
            existing.picture = picture
            updated = True

        if updated:
            existing.oidc_provider = oidc_provider
            existing.oidc_subject = oidc_subject
            return update_person(db, existing)
        return existing

    # Person doesn't exist -- create new one
    new_person = PersonEntity(
        google_id=oidc_subject if oidc_provider == "google" else "",
        oidc_provider=oidc_provider,
        oidc_subject=oidc_subject,
        email=email,
        name=name,
        picture=picture,
    )
    new_person = create_person(db, new_person)
    _provision_new_user_defaults(db, new_person)
    return new_person


def create_user_with_password(
    db: StandardDatabase,
    username: str,
    name: str,
    password_hash: str,
    email: str = "",
) -> PersonEntity:
    """Create a new user with a password credential (no upstream OIDC).

    ``username`` is the unique login identifier (required).
    ``email`` is optional — used for recovery and OTP flows if provided.
    """
    username = (username or "").strip()
    email = (email or "").strip().lower()
    name = (name or username).strip() or "User"

    if not username:
        raise ValueError("Username is required")

    # Allow-list check uses email when available; always allowed when no lists configured
    if email and not is_person_allowed(None, email):
        logger.warning("Password registration denied: email=%r", email)
        raise PermissionError("Person is not allowed to access this system")

    existing_username = get_user_by_username(db, username)
    if existing_username:
        raise ValueError("Username already taken")

    if email:
        existing_email = get_user_by_email(db, email)
        if existing_email:
            raise ValueError("Email already registered")

    new_person = PersonEntity(
        username=username,
        email=email,
        name=name,
        password_hash=password_hash,
    )
    new_person = create_person(db, new_person)
    _provision_new_user_defaults(db, new_person)
    return new_person

def get_or_create_user_by_email(
    db: StandardDatabase,
    email: str,
) -> PersonEntity:
    """Get or create a user by email alone (no password, no OIDC).

    Used for OTP login where the user authenticates via email code.
    If the user doesn't exist, creates one with password_hash=None.
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Valid email is required")

    if not is_person_allowed(None, email):
        raise PermissionError("Person is not allowed to access this system")

    existing = get_user_by_email(db, email)
    if existing:
        return existing

    new_person = PersonEntity(
        email=email,
        name=email.split("@")[0],
    )
    new_person = create_person(db, new_person)
    _provision_new_user_defaults(db, new_person)
    return new_person


def link_oidc_identity(
    db: StandardDatabase,
    user_id: str,
    oidc_provider: str,
    oidc_subject: str,
) -> PersonEntity:
    """Link an OIDC identity (provider + subject) to an existing user.

    Raises ValueError if the identity is already claimed by a different account.
    Idempotent: if already linked to this user, returns the user unchanged.
    """
    # Check whether this identity is already claimed
    existing = get_user_by_oidc_identity(db, oidc_provider, oidc_subject)
    if existing:
        if str(existing.id) == user_id:
            return existing  # Already linked to this user — nothing to do
        raise ValueError("This identity is already linked to another account")

    # Also block if the user already has a *different* OIDC identity linked
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("User not found")
    if user.oidc_provider and user.oidc_subject:
        raise ValueError(
            f"Account already linked to {user.oidc_provider}. Unlink first."
        )

    user.oidc_provider = oidc_provider
    user.oidc_subject = oidc_subject
    if oidc_provider == "google":
        user.google_id = oidc_subject
    return update_person(db, user)


def unlink_oidc_identity(db: StandardDatabase, user_id: str) -> PersonEntity:
    """Remove OIDC identity from a user.

    Only allowed when the user has a password set (so they can still log in).
    """
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("User not found")
    if not getattr(user, "password_hash", None):
        raise ValueError("Cannot unlink: no password is set on this account")
    if not user.oidc_provider:
        raise ValueError("No linked identity to remove")

    user.oidc_provider = ""
    user.oidc_subject = ""
    return update_person(db, user)

def update_person_preferences(db: StandardDatabase, person_id: str, preferences: Dict) -> PersonEntity:
    """
    Update a person's preferences (merges with existing preferences).
    """
    doc = arango_ws.get_person_by_id(db, person_id)
    if not doc:
        raise ValueError(f"Person {person_id} not found")
    person = PersonEntity.from_dict(doc)

    # Merge new preferences with existing
    current_prefs = person.preferences or {}
    current_prefs.update(preferences)
    person.preferences = current_prefs

    ok = arango_ws.update_person_preferences(db, person_id, current_prefs)
    if not ok:
        raise RuntimeError(f"Failed to update preferences for person {person_id}")
    return person
