"""Origin grant service — Postgres-backed.

Ported from Mantle's `services/grant_service.py`. Removes the Arango
`is_creator` fast-path (artifacts live on Mantle; Origin can't read them
without an HTTP round-trip and the spec doesn't define a creator-implies-admin
rule anyway). Origin grants are the sole source of access truth.

Cross-service side effects in this scope:
- `_send_invite_email` uses Origin's email_service. Resource title is a
  generic placeholder (Mantle-side artifact lookup is a follow-up).
- Event emission (`grant.invite.created` / `grant.invite.claimed`) is logged
  only. Cross-service event delivery to Mantle's event_bus is a follow-up.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from origin.db import grants as db_grants
from origin.models.grant import Grant

logger = logging.getLogger(__name__)

_INVITE_TOKEN_PREFIX = "agc_"
_INVITE_TOKEN_BYTES = 32

# Role presets — identical surface to Mantle's GrantEntity.ROLE_PRESETS.
ROLE_PRESETS: dict[str, dict[str, bool]] = {
    "viewer": {"can_read": True},
    "editor": {
        "can_create": True,
        "can_read": True,
        "can_update": True,
        "can_delete": True,
        "can_evict": True,
    },
    "collaborator": {
        "can_create": True,
        "can_read": True,
        "can_update": True,
        "can_delete": True,
        "can_evict": True,
        "can_invoke": True,
        "can_add": True,
        "can_share": True,
    },
    "admin": {
        "can_create": True,
        "can_read": True,
        "can_update": True,
        "can_delete": True,
        "can_evict": True,
        "can_invoke": True,
        "can_add": True,
        "can_share": True,
        "can_admin": True,
    },
}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_claim_token() -> str:
    return f"{_INVITE_TOKEN_PREFIX}{secrets.token_urlsafe(_INVITE_TOKEN_BYTES)}"


def permissions_for_role(role: str) -> dict[str, bool]:
    preset = ROLE_PRESETS.get(role)
    if preset is None:
        raise ValueError(f"Unknown role {role!r}; valid roles: {sorted(ROLE_PRESETS)}")
    return dict(preset)


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------
def user_has_any_flag(
    db: Session, user_id: str, resource_id: str, *flags: str
) -> bool:
    if not user_id:
        return False
    grants = db_grants.get_active_for_principal_resource(
        db, grantee_id=user_id, resource_id=resource_id
    )
    for g in grants:
        for flag in flags:
            if getattr(g, flag, False):
                return True
    return False


def can_share(db: Session, user_id: str, resource_id: str) -> bool:
    return user_has_any_flag(db, user_id, resource_id, "can_share", "can_admin")


def can_admin(db: Session, user_id: str, resource_id: str) -> bool:
    return user_has_any_flag(db, user_id, resource_id, "can_admin")


# ---------------------------------------------------------------------------
# Invite creation
# ---------------------------------------------------------------------------
def create_invite(
    db: Session,
    *,
    user_id: str,
    resource_id: str,
    role: str = "viewer",
    target_email: Optional[str] = None,
    max_claims: Optional[int] = 1,
    name: Optional[str] = None,
    notes: Optional[str] = None,
    expires_at: Optional[str] = None,
    message: Optional[str] = None,
    send_email: bool = True,
) -> Tuple[Grant, str]:
    preset = permissions_for_role(role)
    raw_token = _generate_claim_token()
    token_hash = _hash_token(raw_token)

    expires_dt = (
        datetime.fromisoformat(expires_at.replace("Z", "+00:00")) if expires_at else None
    )
    grant = db_grants.create(
        db,
        {
            "resource_id": resource_id,
            "grantee_type": "invite",
            "grantee_id": token_hash,
            "granted_by": user_id,
            "can_create": preset.get("can_create", False),
            "can_read": preset.get("can_read", True),
            "can_update": preset.get("can_update", False),
            "can_delete": preset.get("can_delete", False),
            "can_evict": preset.get("can_evict", False),
            "can_invoke": preset.get("can_invoke", False),
            "can_add": preset.get("can_add", False),
            "can_share": preset.get("can_share", False),
            "can_admin": preset.get("can_admin", False),
            "requires_identity": bool(target_email),
            "target_entity": target_email.lower() if target_email else None,
            "target_entity_type": "email" if target_email else None,
            "max_claims": max_claims,
            "state": "active",
            "name": name,
            "notes": notes,
            "granted_at": datetime.now(timezone.utc),
            "expires_at": expires_dt,
        },
    )

    email_sent = False
    if send_email and target_email:
        email_sent = _send_invite_email(target_email, raw_token, message)
    _emit_invite_event(
        resource_id,
        "grant.invite.created",
        {
            "grant_id": str(grant.id),
            "role": role,
            "target_email": target_email,
            "email_sent": email_sent,
        },
        actor_id=user_id,
    )
    return grant, raw_token


def build_claim_url(raw_token: str) -> str:
    """Public claim URL for an invite token."""
    from kernel.config import AUTHORITY_ISSUER

    return f"{AUTHORITY_ISSUER}/invite/{raw_token}"


def _send_invite_email(target_email: str, raw_token: str, message: Optional[str]) -> bool:
    from origin.services import email_service

    claim_url = build_claim_url(raw_token)
    try:
        return _run_async(
            email_service.send_invite(
                target_email,
                from_name="Someone",  # follow-up: lookup via Postgres person
                resource_name="a workspace",  # follow-up: cross-service artifact title
                claim_url=claim_url,
                message=message,
            )
        )
    except Exception:
        logger.warning("send_invite email delivery failed", exc_info=True)
        return False


def _run_async(coro):
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _emit_invite_event(
    resource_id: str,
    event_name: str,
    data: dict,
    *,
    actor_id: Optional[str] = None,
) -> None:
    """Log-only emission. Cross-service event delivery to Mantle is a follow-up."""
    logger.info(
        "[invite-event] %s resource=%s actor=%s data=%s",
        event_name, resource_id, actor_id, data,
    )


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------
class InviteClaimError(Exception):
    """Base for expected claim failures."""


class InviteNotFound(InviteClaimError):
    pass


class InviteExhausted(InviteClaimError):
    pass


class InviteIdentityMismatch(InviteClaimError):
    pass


def claim_invite(db: Session, user_id: str, raw_token: str) -> Grant:
    invite = _lookup_active_invite(db, raw_token)
    if invite.target_entity and invite.target_entity_type:
        _verify_target_match(db, user_id, invite)
    if invite.max_claims is not None and (invite.claims_count or 0) >= invite.max_claims:
        raise InviteExhausted("Invite has reached its claim limit")

    new_grant = db_grants.create(
        db,
        {
            "resource_id": str(invite.resource_id),
            "grantee_type": "user",
            "grantee_id": user_id,
            "granted_by": str(invite.granted_by),
            "can_create": invite.can_create,
            "can_read": invite.can_read,
            "can_update": invite.can_update,
            "can_delete": invite.can_delete,
            "can_evict": invite.can_evict,
            "can_invoke": invite.can_invoke,
            "can_add": invite.can_add,
            "can_share": invite.can_share,
            "can_admin": invite.can_admin,
            "requires_identity": True,
            "state": "active",
            "name": invite.name,
            "notes": f"Claimed from invite {invite.id}",
            "granted_at": datetime.now(timezone.utc),
            "expires_at": invite.expires_at,
        },
    )

    update_fields: dict = {"claims_count": (invite.claims_count or 0) + 1}
    if invite.max_claims == 1:
        update_fields["state"] = "revoked"
        update_fields["revoked_at"] = datetime.now(timezone.utc)
        update_fields["revoked_by"] = user_id
    db_grants.update_grant(db, str(invite.id), update_fields)

    logger.info(
        "invite claimed: invite=%s resource=%s user=%s",
        invite.id, invite.resource_id, user_id,
    )
    _emit_invite_event(
        str(invite.resource_id),
        "grant.invite.claimed",
        {
            "grant_id": str(new_grant.id),
            "invite_id": str(invite.id),
            "user_id": user_id,
        },
        actor_id=user_id,
    )
    return new_grant


def list_invites_sent(
    db: Session, user_id: str, include_revoked: bool = False
) -> list[Grant]:
    return db_grants.list_invites_sent(db, user_id, include_revoked=include_revoked)


# ---------------------------------------------------------------------------
# Pre/post-auth context
# ---------------------------------------------------------------------------
def get_invite_context(db: Session, raw_token: str) -> Optional[dict]:
    try:
        invite = _lookup_active_invite(db, raw_token)
    except InviteClaimError:
        return None
    return {
        "valid": True,
        "has_target": bool(invite.target_entity),
        "target_type": invite.target_entity_type,
    }


def get_invite_details(db: Session, raw_token: str, user_id: str) -> Optional[dict]:
    try:
        invite = _lookup_active_invite(db, raw_token)
    except InviteClaimError:
        return None
    if invite.target_entity and invite.target_entity_type:
        try:
            _verify_target_match(db, user_id, invite)
        except InviteIdentityMismatch:
            return {"valid": True, "identity_mismatch": True}
    return {
        "valid": True,
        "resource_id": str(invite.resource_id),
        "granted_by": str(invite.granted_by),
        "name": invite.name,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _lookup_active_invite(db: Session, raw_token: str) -> Grant:
    candidates = db_grants.get_active_by_key(db, raw_token)
    if not candidates:
        raise InviteNotFound("Invite not found or expired")
    invite = candidates[0]
    if invite.grantee_type != "invite":
        raise InviteNotFound("Not an invite grant")
    if invite.state != "active":
        raise InviteExhausted("Invite is no longer active")
    return invite


def _verify_target_match(db: Session, user_id: str, invite: Grant) -> None:
    from origin.db import persons as db_persons

    match = False
    target_type = invite.target_entity_type
    target = invite.target_entity or ""

    if target_type == "user_id":
        match = user_id == target
    elif target_type in ("email", "domain"):
        person = db_persons.get_by_id(db, user_id)
        email = (person.email or "").lower() if person else ""
        if email:
            if target_type == "email":
                match = email == target.lower()
            else:
                match = email.endswith("@" + target.lower())

    if not match:
        raise InviteIdentityMismatch("You are not the intended recipient of this invite")


# ---------------------------------------------------------------------------
# Upsert helper (used by setup wizard / seeders via internal endpoint)
# ---------------------------------------------------------------------------
def upsert_user_grant(
    db: Session,
    *,
    user_id: str,
    resource_id: str,
    granted_by: str,
    flags: dict,
    name: Optional[str] = None,
) -> Tuple[Grant, bool]:
    """Idempotent user→resource grant. Returns (grant, changed).

    Used by Mantle-side seeders that need to grant the operator on platform
    collections at setup. Server-to-server endpoint exposes this.
    """
    existing = db_grants.find_existing_user_grant(db, user_id=user_id, resource_id=resource_id)
    flag_names = (
        "can_create",
        "can_read",
        "can_update",
        "can_delete",
        "can_evict",
        "can_invoke",
        "can_add",
        "can_share",
        "can_admin",
    )
    desired = {f: bool(flags.get(f, False)) for f in flag_names}
    if existing is not None:
        current = {f: bool(getattr(existing, f, False)) for f in flag_names}
        if current == desired:
            return existing, False
        updated = db_grants.update_grant(db, str(existing.id), desired)
        return (updated or existing), True

    grant = db_grants.create(
        db,
        {
            "resource_id": resource_id,
            "grantee_type": "user",
            "grantee_id": user_id,
            "granted_by": granted_by,
            **desired,
            "state": "active",
            "name": name,
            "granted_at": datetime.now(timezone.utc),
        },
    )
    return grant, True
