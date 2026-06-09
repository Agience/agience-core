"""Origin /auth/grants router — CRUDEASIO grant management.

Phase A rename: `/grants` → `/auth/grants`. Postgres-backed via
`origin.services.grant_service`.

Server-to-server endpoints (kernel-callers only):
- `GET /auth/grants/check` — direct grant resolution for `check_access`
- `POST /auth/grants/lookup-by-key` — bearer-grant-key path of `resolve_auth`
- `POST /auth/grants/internal/upsert` — idempotent user grant for seeders
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from origin.db import grants as db_grants
from origin.db.session import get_db
from origin.models.grant import Grant
from origin.services import grant_service
from origin.services.dependencies import AuthContext, get_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/grants", tags=["Grants"])
internal_router = APIRouter(
    prefix="/auth/grants", tags=["Grants (internal)"], include_in_schema=False
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ClaimInviteRequest(BaseModel):
    token: str


class CreateGrantRequest(BaseModel):
    resource_id: str
    can_create: bool = False
    can_read: bool = True
    can_update: bool = False
    can_delete: bool = False
    can_invoke: bool = False
    can_add: bool = False
    can_share: bool = False
    can_admin: bool = False
    grantee_type: str = "user"
    grantee_id: Optional[str] = None
    target_entity: Optional[str] = None
    target_entity_type: Optional[str] = None
    max_claims: Optional[int] = None
    requires_identity: bool = False
    name: Optional[str] = None
    notes: Optional[str] = None
    expires_at: Optional[str] = None
    state: str = "active"
    role: Optional[str] = None
    message: Optional[str] = None


class LookupByKeyRequest(BaseModel):
    token: str


class UpsertUserGrantRequest(BaseModel):
    user_id: str
    resource_id: str
    granted_by: str
    flags: dict
    name: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _grant_response(g: Grant) -> dict:
    """Mirror entities.Grant.to_dict() shape so existing callers don't break."""
    return {
        "id": str(g.id),
        "resource_id": str(g.resource_id),
        "grantee_type": g.grantee_type,
        "grantee_id": g.grantee_id,
        "granted_by": str(g.granted_by),
        "effect": g.effect,
        "can_create": g.can_create,
        "can_read": g.can_read,
        "can_update": g.can_update,
        "can_delete": g.can_delete,
        "can_evict": g.can_evict,
        "can_invoke": g.can_invoke,
        "can_add": g.can_add,
        "can_share": g.can_share,
        "can_admin": g.can_admin,
        "requires_identity": g.requires_identity,
        "read_requires_identity": g.read_requires_identity,
        "write_requires_identity": g.write_requires_identity,
        "invoke_requires_identity": g.invoke_requires_identity,
        "target_entity": g.target_entity,
        "target_entity_type": g.target_entity_type,
        "max_claims": g.max_claims,
        "claims_count": g.claims_count,
        "state": g.state,
        "name": g.name,
        "notes": g.notes,
        "granted_at": g.granted_at.isoformat() if g.granted_at else None,
        "expires_at": g.expires_at.isoformat() if g.expires_at else None,
        "accepted_by": str(g.accepted_by) if g.accepted_by else None,
        "accepted_at": g.accepted_at.isoformat() if g.accepted_at else None,
        "revoked_by": str(g.revoked_by) if g.revoked_by else None,
        "revoked_at": g.revoked_at.isoformat() if g.revoked_at else None,
        "created_time": g.created_time.isoformat() if g.created_time else None,
        "modified_time": g.modified_time.isoformat() if g.modified_time else None,
    }


def _require_admin(auth: AuthContext, resource_id: str, db: Session) -> None:
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    if not grant_service.can_admin(db, auth.user_id, resource_id):
        raise HTTPException(
            status_code=403,
            detail="Only an admin grant on the resource can manage grants",
        )


def _require_share_or_admin(auth: AuthContext, resource_id: str, db: Session) -> None:
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    if not grant_service.can_share(db, auth.user_id, resource_id):
        raise HTTPException(
            status_code=403, detail="You need share or admin permission on this resource"
        )


def _require_kernel_server(auth: AuthContext) -> None:
    """Accept either a kernel mutual service JWT (post-1.1d: principal_type=service,
    iss in {mantle, chorus}) or a legacy MCP-server client_credentials token
    (principal_type=server, client_id in the kernel_servers registry)."""
    if auth.principal_type == "service":
        if auth.principal_id in {"mantle", "chorus"}:
            return
        raise HTTPException(status_code=403, detail="Caller is not a recognized kernel service")
    if auth.principal_type == "server":
        from origin.services import kernel_servers

        if auth.principal_id not in set(kernel_servers.all_client_ids()):
            raise HTTPException(status_code=403, detail="Caller is not a recognized kernel server")
        return
    raise HTTPException(status_code=403, detail="Kernel caller required")


# ---------------------------------------------------------------------------
# Endpoints (user-facing)
# ---------------------------------------------------------------------------
@router.get("/invite-context")
async def get_invite_context_endpoint(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    ctx = grant_service.get_invite_context(db, token)
    if not ctx:
        raise HTTPException(status_code=404, detail="Invite not found or expired")
    return ctx


@router.get("/invite-details")
async def get_invite_details_endpoint(
    token: str = Query(...),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    details = grant_service.get_invite_details(db, token, auth.user_id)
    if not details:
        raise HTTPException(status_code=404, detail="Invite not found or expired")
    return details


@router.get("/mine-sent")
async def list_invites_sent_endpoint(
    include_revoked: bool = Query(False),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    grants = grant_service.list_invites_sent(db, auth.user_id, include_revoked=include_revoked)
    return [_grant_response(g) for g in grants]


@router.post("/claim", status_code=status.HTTP_201_CREATED)
async def claim_invite_endpoint(
    body: ClaimInviteRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    try:
        created = grant_service.claim_invite(db, auth.user_id, body.token)
    except grant_service.InviteIdentityMismatch as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc))
    except grant_service.InviteExhausted as exc:
        db.rollback()
        raise HTTPException(status_code=410, detail=str(exc))
    except grant_service.InviteNotFound as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return _grant_response(created)


@router.get("")
async def list_grants_endpoint(
    resource_id: str = Query(...),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    _require_admin(auth, resource_id, db)
    grants = db_grants.list_for_resource(db, resource_id)
    return [_grant_response(g) for g in grants]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_grant_endpoint(
    body: CreateGrantRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")

    if body.grantee_type == "invite":
        _require_share_or_admin(auth, body.resource_id, db)
        target_email = (
            body.target_entity if (body.target_entity_type or "").lower() == "email" else None
        )
        role = body.role or _role_from_bits(body) or "viewer"
        try:
            created, raw_token = grant_service.create_invite(
                db,
                user_id=auth.user_id,
                resource_id=body.resource_id,
                role=role,
                target_email=target_email,
                max_claims=body.max_claims if body.max_claims is not None else 1,
                name=body.name,
                notes=body.notes,
                expires_at=body.expires_at,
                message=body.message,
            )
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))
        db.commit()
        response = _grant_response(created)
        response["claim_token"] = raw_token
        response["claim_url"] = grant_service.build_claim_url(raw_token)
        return response

    _require_admin(auth, body.resource_id, db)
    expires_dt = (
        datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
        if body.expires_at
        else None
    )
    grant = db_grants.create(
        db,
        {
            "resource_id": body.resource_id,
            "grantee_type": body.grantee_type,
            "grantee_id": body.grantee_id or "",
            "granted_by": auth.user_id,
            "can_create": body.can_create,
            "can_read": body.can_read,
            "can_update": body.can_update,
            "can_delete": body.can_delete,
            "can_invoke": body.can_invoke,
            "can_add": body.can_add,
            "can_share": body.can_share,
            "can_admin": body.can_admin,
            "requires_identity": body.requires_identity,
            "target_entity": body.target_entity,
            "target_entity_type": body.target_entity_type,
            "max_claims": body.max_claims,
            "state": body.state,
            "name": body.name,
            "notes": body.notes,
            "granted_at": datetime.now(timezone.utc),
            "expires_at": expires_dt,
        },
    )
    db.commit()
    return _grant_response(grant)


def _role_from_bits(body: CreateGrantRequest) -> Optional[str]:
    actual = {
        "can_create": body.can_create,
        "can_read": body.can_read,
        "can_update": body.can_update,
        "can_delete": body.can_delete,
        "can_invoke": body.can_invoke,
        "can_add": body.can_add,
        "can_share": body.can_share,
        "can_admin": body.can_admin,
    }
    enabled = {k for k, v in actual.items() if v}
    for role_name, preset in grant_service.ROLE_PRESETS.items():
        preset_enabled = {k for k, v in preset.items() if v}
        if enabled == preset_enabled:
            return role_name
    return None


@router.get("/{grant_id}")
async def read_grant(
    grant_id: str,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    grant = db_grants.get_by_id(db, grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Grant not found")

    is_grantee = grant.grantee_id == auth.user_id
    is_granter = str(grant.granted_by) == auth.user_id
    if not is_grantee and not is_granter:
        try:
            _require_admin(auth, str(grant.resource_id), db)
        except HTTPException:
            raise HTTPException(status_code=404, detail="Grant not found")
    return _grant_response(grant)


@router.delete("/{grant_id}")
async def revoke_grant(
    grant_id: str,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    grant = db_grants.get_by_id(db, grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Grant not found")

    is_revocable_invite = (
        str(grant.granted_by) == auth.user_id and grant.grantee_type == "invite"
    )
    if not is_revocable_invite:
        _require_admin(auth, str(grant.resource_id), db)

    now = datetime.now(timezone.utc)
    updated = db_grants.update_grant(
        db,
        grant_id,
        {"state": "revoked", "revoked_by": auth.user_id, "revoked_at": now},
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to revoke grant")
    db.commit()
    return {"id": grant_id, "state": "revoked"}


@router.post("/{grant_id}/accept")
async def accept_grant(
    grant_id: str,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    grant = db_grants.get_by_id(db, grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Grant not found")
    if grant.state != "pending_accept":
        raise HTTPException(status_code=400, detail="Grant is not pending acceptance")
    if grant.grantee_id != auth.user_id:
        raise HTTPException(status_code=403, detail="Only the grantee can accept this grant")

    now = datetime.now(timezone.utc)
    updated = db_grants.update_grant(
        db,
        grant_id,
        {"state": "active", "accepted_by": auth.user_id, "accepted_at": now},
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to accept grant")
    db.commit()
    return _grant_response(updated)


# ---------------------------------------------------------------------------
# Internal endpoints (kernel-server auth)
# ---------------------------------------------------------------------------
_ACTION_FLAG_MAP = {
    "create": "can_create",
    "read": "can_read",
    "update": "can_update",
    "delete": "can_delete",
    "evict": "can_evict",
    "invoke": "can_invoke",
    "add": "can_add",
    "share": "can_share",
    "admin": "can_admin",
}


@internal_router.get("/check")
def check_grant(
    resource: str = Query(..., alias="resource"),
    principal: str = Query(..., alias="principal"),
    action: str = Query("read"),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    """Direct grant check for a (principal, resource, action) triple.

    Returns `{allowed: bool, grant_id: str|null, flags: list[str], effect: str}`.
    Only checks DIRECT grants on the resource — origin-edge propagation is
    walked by Mantle (edges live in Arango).
    """
    _require_kernel_server(auth)
    flag_attr = _ACTION_FLAG_MAP.get(action)
    if not flag_attr:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
    grants = db_grants.get_active_for_principal_resource(
        db, grantee_id=principal, resource_id=resource
    )
    # Deny before allow.
    for g in grants:
        if g.effect == "deny" and getattr(g, flag_attr, False):
            return {"allowed": False, "grant_id": str(g.id), "flags": [], "effect": "deny"}
    for g in grants:
        if g.effect != "deny" and getattr(g, flag_attr, False):
            flags = [
                action_name
                for action_name, attr in _ACTION_FLAG_MAP.items()
                if getattr(g, attr, False)
            ]
            return {
                "allowed": True,
                "grant_id": str(g.id),
                "flags": flags,
                "effect": "allow",
            }
    return {"allowed": False, "grant_id": None, "flags": [], "effect": "allow"}


@internal_router.post("/lookup-by-key")
def lookup_by_key(
    body: LookupByKeyRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    """Resolve a Bearer-presented invite token to its active grants.

    Token in body (not query) so it doesn't appear in URLs/logs.
    """
    _require_kernel_server(auth)
    grants = db_grants.get_active_by_key(db, body.token)
    return {"grants": [_grant_response(g) for g in grants]}


@internal_router.get("/by-principal-resource")
def list_by_principal_resource(
    grantee_id: str = Query(...),
    resource_id: str = Query(...),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    """All active grants where this grantee has any flag on this resource."""
    _require_kernel_server(auth)
    grants = db_grants.get_active_for_principal_resource(
        db, grantee_id=grantee_id, resource_id=resource_id
    )
    return {"grants": [_grant_response(g) for g in grants]}


@internal_router.get("/by-grantee")
def list_by_grantee(
    grantee_id: str = Query(...),
    grantee_type: str = Query("user"),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    _require_kernel_server(auth)
    grants = db_grants.get_active_for_grantee(db, grantee_id, grantee_type)
    return {"grants": [_grant_response(g) for g in grants]}


@internal_router.post("/upsert")
def upsert_user_grant(
    body: UpsertUserGrantRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    """Idempotent user→resource grant. Used by Mantle-side seeders that need to
    grant the operator on platform collections at setup time.
    """
    _require_kernel_server(auth)
    grant, changed = grant_service.upsert_user_grant(
        db,
        user_id=body.user_id,
        resource_id=body.resource_id,
        granted_by=body.granted_by,
        flags=body.flags,
        name=body.name,
    )
    db.commit()
    return {"grant": _grant_response(grant), "changed": changed}

