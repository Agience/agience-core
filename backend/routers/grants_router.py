# routers/grants_router.py
#
# Grant management endpoints — invite claim, CRUD, accept.

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from arango.database import StandardDatabase
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from core.dependencies import get_arango_db
from services.dependencies import get_auth, AuthContext
from db.arango import (
    create_grant,
    get_grant_by_id,
    update_grant,
    get_active_grants_for_principal_resource as db_get_active_grants,
)
from services.auth_service import hash_api_key
from entities.grant import Grant as GrantEntity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/grants", tags=["Grants"])


# =============================================================================
# Request / Response Models
# =============================================================================

class ClaimInviteRequest(BaseModel):
    token: str


class CreateGrantRequest(BaseModel):
    resource_id: str
    resource_type: str = "collection"
    # CRUDIASO
    can_create: bool = False
    can_read: bool = True
    can_update: bool = False
    can_delete: bool = False
    can_invoke: bool = False
    can_add: bool = False
    can_search: bool = False
    can_own: bool = False
    # Invite targeting (optional — makes this an invite grant)
    grantee_type: str = "user"              # "user" | "invite"
    grantee_id: Optional[str] = None        # user_id for direct grant; omit for invite
    target_entity: Optional[str] = None     # email, domain, etc. (invite only)
    target_entity_type: Optional[str] = None
    max_claims: Optional[int] = None
    requires_identity: bool = False
    name: Optional[str] = None
    notes: Optional[str] = None
    expires_at: Optional[str] = None
    state: str = "active"




# =============================================================================
# Helpers
# =============================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _grant_response(grant: GrantEntity) -> dict:
    """Serialize a grant entity for API responses."""
    return grant.to_dict()


def _require_owner_or_can_own(
    auth: AuthContext,
    resource_id: str,
    resource_type: str,
    arango_db: StandardDatabase,
) -> None:
    """Raise 403 unless the caller owns the resource or has can_own."""
    # Try to find the resource document and check ownership.
    try:
        coll = arango_db.collection("artifacts")
        doc = coll.get(resource_id)
        if doc:
            owner_id = doc.get("created_by")
            if owner_id and auth.user_id and owner_id == auth.user_id:
                return  # owner — allowed
    except Exception:
        pass

    # Not the owner — check for can_own grant.
    if auth.user_id:
        grants = db_get_active_grants(
            arango_db,
            grantee_id=auth.user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        for g in grants:
            if getattr(g, "can_own", False) and g.is_active():
                return

    raise HTTPException(status_code=403, detail="Only the resource owner can manage grants")


# =============================================================================
# Endpoints
# =============================================================================

# ---------- POST /grants/claim — Claim an invite ----------

@router.post("/claim", status_code=status.HTTP_201_CREATED)
async def claim_invite(
    body: ClaimInviteRequest,
    auth: AuthContext = Depends(get_auth),
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """Claim an invite grant by presenting the raw invite token."""
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")

    # 1. Hash the presented token.
    token_hash = hash_api_key(body.token)

    # 2. Look up the invite grant by grantee_id (the hash).
    #    The grant's _key may not be the hash, so search by grantee_id + type.
    from db.arango import get_active_grants_for_grantee
    candidates = get_active_grants_for_grantee(arango_db, token_hash, "invite")
    if not candidates:
        raise HTTPException(status_code=404, detail="Invite not found or expired")
    invite = candidates[0]

    if invite.grantee_type != GrantEntity.GRANTEE_INVITE:
        raise HTTPException(status_code=400, detail="Not an invite grant")

    if invite.state != GrantEntity.STATE_ACTIVE:
        raise HTTPException(status_code=410, detail="Invite is no longer active")

    # 3. If target_entity is set, verify the claimant matches.
    if invite.target_entity and invite.target_entity_type:
        match = False
        if invite.target_entity_type == "user_id":
            match = auth.user_id == invite.target_entity
        elif invite.target_entity_type == "email":
            # Look up the user's email from their person record.
            try:
                from services.person_service import get_user_by_id
                person = get_user_by_id(db=arango_db, id=auth.user_id)
                if person and getattr(person, "email", None):
                    match = person.email.lower() == invite.target_entity.lower()
            except Exception:
                pass
        elif invite.target_entity_type == "domain":
            try:
                from services.person_service import get_user_by_id
                person = get_user_by_id(db=arango_db, id=auth.user_id)
                if person and getattr(person, "email", None):
                    match = person.email.lower().endswith("@" + invite.target_entity.lower())
            except Exception:
                pass

        if not match:
            raise HTTPException(status_code=403, detail="You are not the intended recipient of this invite")

    # 4. If max_claims is set and claims_count >= max_claims, reject.
    if invite.max_claims is not None and invite.claims_count >= invite.max_claims:
        raise HTTPException(status_code=410, detail="Invite has reached its claim limit")

    # 5. Create a new user grant with the same permissions.
    now = _now_iso()
    new_grant = GrantEntity(
        id=str(uuid.uuid4()),
        resource_type=invite.resource_type,
        resource_id=invite.resource_id,
        grantee_type=GrantEntity.GRANTEE_USER,
        grantee_id=auth.user_id,
        granted_by=invite.granted_by,
        can_create=invite.can_create,
        can_read=invite.can_read,
        can_update=invite.can_update,
        can_delete=invite.can_delete,
        can_invoke=invite.can_invoke,
        can_add=invite.can_add,
        can_search=invite.can_search,
        can_own=invite.can_own,
        requires_identity=True,
        state=GrantEntity.STATE_ACTIVE,
        name=invite.name,
        notes=f"Claimed from invite {invite.id}",
        granted_at=now,
        expires_at=invite.expires_at,
        created_time=now,
        modified_time=now,
    )
    created = create_grant(arango_db, new_grant)

    # 6. Increment claims_count on the invite.
    invite.claims_count += 1
    invite.modified_time = now

    # 7. If max_claims == 1, auto-revoke the invite.
    if invite.max_claims == 1:
        invite.state = GrantEntity.STATE_REVOKED
        invite.revoked_at = now
        invite.revoked_by = auth.user_id

    update_grant(arango_db, invite)

    return _grant_response(created)


# ---------- GET /grants — List grants for a resource ----------

@router.get("")
async def list_grants_endpoint(
    resource_id: str = Query(..., description="Resource ID to list grants for"),
    resource_type: str = Query("collection", description="Resource type"),
    auth: AuthContext = Depends(get_auth),
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """List all grants on a resource. Only the resource owner (or can_own) can list."""
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")

    _require_owner_or_can_own(auth, resource_id, resource_type, arango_db)

    from db.arango import get_grants_for_collection, query_documents, COLLECTION_GRANTS
    from entities.grant import Grant as GrantEntity

    if resource_type == "collection":
        grants = get_grants_for_collection(arango_db, resource_id)
    else:
        grants = query_documents(
            arango_db, GrantEntity, COLLECTION_GRANTS,
            {"resource_type": resource_type, "resource_id": resource_id},
        )

    return [_grant_response(g) for g in grants]


# ---------- POST /grants — Create a grant or invite ----------

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_grant_endpoint(
    body: CreateGrantRequest,
    auth: AuthContext = Depends(get_auth),
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """Create a new grant or invite.

    Only the resource owner (or someone with can_own) can create grants.
    """
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")

    _require_owner_or_can_own(auth, body.resource_id, body.resource_type, arango_db)

    now = _now_iso()

    # For invite grants, generate a claim token if no grantee_id is provided.
    grantee_id = body.grantee_id or ""
    raw_token: Optional[str] = None

    if body.grantee_type == GrantEntity.GRANTEE_INVITE and not grantee_id:
        import secrets
        raw_token = f"agc_{secrets.token_urlsafe(32)}"
        grantee_id = hash_api_key(raw_token)

    grant = GrantEntity(
        id=str(uuid.uuid4()),
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        grantee_type=body.grantee_type,
        grantee_id=grantee_id,
        granted_by=auth.user_id,
        can_create=body.can_create,
        can_read=body.can_read,
        can_update=body.can_update,
        can_delete=body.can_delete,
        can_invoke=body.can_invoke,
        can_add=body.can_add,
        can_search=body.can_search,
        can_own=body.can_own,
        requires_identity=body.requires_identity,
        target_entity=body.target_entity,
        target_entity_type=body.target_entity_type,
        max_claims=body.max_claims,
        state=body.state,
        name=body.name,
        notes=body.notes,
        granted_at=now,
        expires_at=body.expires_at,
        created_time=now,
        modified_time=now,
    )

    created = create_grant(arango_db, grant)
    response = _grant_response(created)

    # Include the raw claim token in the response (only on creation).
    if raw_token:
        response["claim_token"] = raw_token

    return response


# ---------- GET /grants/{grant_id} — Read a grant ----------

@router.get("/{grant_id}")
async def read_grant(
    grant_id: str,
    auth: AuthContext = Depends(get_auth),
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """Read a single grant by ID."""
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")

    grant = get_grant_by_id(arango_db, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    # Visible to: the grantee, the granter, or someone with can_own on the resource.
    is_grantee = grant.grantee_id == auth.user_id
    is_granter = grant.granted_by == auth.user_id
    if not is_grantee and not is_granter:
        # Check can_own on the resource.
        try:
            _require_owner_or_can_own(auth, grant.resource_id, grant.resource_type, arango_db)
        except HTTPException:
            raise HTTPException(status_code=404, detail="Grant not found")

    return _grant_response(grant)


# ---------- PATCH /grants/{grant_id} — Removed (immutable grants) ----------
# Grants are immutable after creation. To change permissions, revoke the old
# grant and create a new one.  This aligns with the FLARE append-only ledger
# model and provides a clean audit trail.


# ---------- DELETE /grants/{grant_id} — Revoke a grant ----------

@router.delete("/{grant_id}")
async def revoke_grant(
    grant_id: str,
    auth: AuthContext = Depends(get_auth),
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """Revoke a grant (soft-delete by setting state to revoked)."""
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")

    grant = get_grant_by_id(arango_db, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    # Only granter or resource owner can revoke.
    is_granter = grant.granted_by == auth.user_id
    if not is_granter:
        _require_owner_or_can_own(auth, grant.resource_id, grant.resource_type, arango_db)

    now = _now_iso()
    grant.state = GrantEntity.STATE_REVOKED
    grant.revoked_by = auth.user_id
    grant.revoked_at = now
    grant.modified_time = now

    updated = update_grant(arango_db, grant)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to revoke grant")

    return {"id": grant_id, "state": "revoked"}


# ---------- POST /grants/{grant_id}/accept — Accept a pending grant ----------

@router.post("/{grant_id}/accept")
async def accept_grant(
    grant_id: str,
    auth: AuthContext = Depends(get_auth),
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """Accept a pending_accept direct grant."""
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")

    grant = get_grant_by_id(arango_db, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    if grant.state != GrantEntity.STATE_PENDING_ACCEPT:
        raise HTTPException(status_code=400, detail="Grant is not pending acceptance")

    # Only the grantee can accept.
    if grant.grantee_id != auth.user_id:
        raise HTTPException(status_code=403, detail="Only the grantee can accept this grant")

    now = _now_iso()
    grant.state = GrantEntity.STATE_ACTIVE
    grant.accepted_by = auth.user_id
    grant.accepted_at = now
    grant.modified_time = now

    updated = update_grant(arango_db, grant)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to accept grant")

    return _grant_response(updated)
