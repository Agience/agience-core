"""Origin /auth/keys router — Postgres-backed personal API keys.

Phase A rename: `/api-keys` → `/auth/keys`. API keys cannot be created by other
API keys (JWT-only via `get_end_user_claims`). The raw key is returned ONCE on
creation; subsequent reads return only metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel as _BaseModel
from sqlalchemy.orm import Session

from origin.api.api_key import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeyUpdate,
)
from origin.db import api_keys as db_api_keys
from origin.db.session import get_db
from origin.models.api_key import ApiKey
from origin.services import auth_service as auth_svc
from origin.services.dependencies import AuthContext, get_auth

router = APIRouter(prefix="/auth/keys", tags=["Personal API Keys"])
internal_router = APIRouter(
    prefix="/auth/keys", tags=["Personal API Keys (internal)"], include_in_schema=False
)

DEFAULT_SCOPES = [
    "resource:*:read",
    "resource:*:search",
    "resource:*:list",
    "resource:*:invoke",
]
DEFAULT_RESOURCE_FILTERS: Dict[str, Any] = {"workspaces": "*", "collections": "*"}


def _to_response(k: ApiKey) -> APIKeyResponse:
    return APIKeyResponse(
        id=str(k.id),
        user_id=str(k.user_id),
        name=k.name,
        client_id=k.client_id,
        host_id=str(k.host_id) if k.host_id else None,
        server_id=str(k.server_id) if k.server_id else None,
        agent_id=str(k.agent_id) if k.agent_id else None,
        display_label=k.display_label,
        issued_by_user_id=str(k.issued_by_user_id) if k.issued_by_user_id else None,
        created_from_client_id=k.created_from_client_id,
        scopes=list(k.scopes or []),
        resource_filters=dict(k.resource_filters or {}),
        created_time=k.created_time.isoformat() if k.created_time else "",
        modified_time=k.modified_time.isoformat() if k.modified_time else None,
        expires_at=k.expires_at.isoformat() if k.expires_at else None,
        last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
        is_active=bool(k.is_active),
    )


def _require_user_jwt(auth: AuthContext) -> str:
    """API keys must be created/managed by an end-user JWT, not another API key."""
    if auth.principal_type != "user" or not auth.user_id:
        raise HTTPException(status_code=403, detail="API key management requires a user JWT")
    return auth.user_id


@router.post("", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: APIKeyCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    user_id = _require_user_jwt(auth)
    raw_key = auth_svc.generate_api_key()
    key_hash = auth_svc.hash_api_key(raw_key)
    expires_at = (
        datetime.fromisoformat(payload.expires_at.replace("Z", "+00:00"))
        if payload.expires_at
        else None
    )
    created = db_api_keys.create(
        db,
        {
            "user_id": user_id,
            "key_hash": key_hash,
            "name": payload.name,
            "client_id": payload.client_id,
            "host_id": payload.host_id,
            "server_id": payload.server_id,
            "agent_id": payload.agent_id,
            "display_label": payload.display_label or "Easy MCP Key",
            "issued_by_user_id": user_id,
            "created_from_client_id": payload.client_id,
            "scopes": payload.scopes or list(DEFAULT_SCOPES),
            "resource_filters": payload.resource_filters
            if payload.resource_filters is not None
            else dict(DEFAULT_RESOURCE_FILTERS),
            "expires_at": expires_at,
            "is_active": True,
        },
    )
    db.commit()
    response = _to_response(created)
    return APIKeyCreateResponse(**response.model_dump(), key=raw_key)


@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return [_to_response(k) for k in db_api_keys.get_by_user(db, auth.user_id)]


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    key = db_api_keys.get_by_id(db, key_id)
    if key is None or str(key.user_id) != str(auth.user_id):
        raise HTTPException(status_code=404, detail="API key not found")
    return _to_response(key)


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: str,
    payload: APIKeyUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    user_id = _require_user_jwt(auth)
    key = db_api_keys.get_by_id(db, key_id)
    if key is None or str(key.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="API key not found")
    fields = payload.model_dump(exclude_unset=True)
    updated = db_api_keys.update(db, key_id, fields)
    db.commit()
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to update API key")
    return _to_response(updated)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    user_id = _require_user_jwt(auth)
    key = db_api_keys.get_by_id(db, key_id)
    if key is None or str(key.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="API key not found")
    if not db_api_keys.delete(db, key_id):
        raise HTTPException(status_code=500, detail="Failed to delete API key")
    db.commit()


# ---------------------------------------------------------------------------
# Internal — Mantle uses this to verify raw `agc_xxx` tokens at request time.
# Caller must present a kernel-server service JWT (Phase C mutual trust).
# ---------------------------------------------------------------------------
class _VerifyApiKeyRequest(_BaseModel):
    token: str


def _require_kernel_server(auth: AuthContext) -> None:
    if auth.principal_type != "server":
        raise HTTPException(status_code=403, detail="Kernel server token required")
    from origin.services import kernel_servers

    kernel_ids = set(kernel_servers.all_client_ids()) | {"agience-mantle"}
    if auth.principal_id not in kernel_ids:
        raise HTTPException(status_code=403, detail="Caller is not a recognized kernel server")


@internal_router.post("/verify")
def internal_verify_api_key(
    payload: _VerifyApiKeyRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    """Server-to-server API key verification.

    Returns the metadata Mantle needs to construct an `AuthContext`: the api_key
    fields plus the active grants for the api_key principal. Updates
    `last_used_at` as a side effect (same as the local verify path).
    """
    _require_kernel_server(auth)
    from origin.services.auth_verifier import verify_api_key as _verify_api_key

    api_key = _verify_api_key(db, payload.token)
    if api_key is None:
        db.commit()
        raise HTTPException(status_code=404, detail="Invalid API key")
    from origin.db import grants as db_grants

    grants = db_grants.get_active_for_grantee(db, str(api_key.id), "api_key")
    db.commit()
    return {
        "api_key": _to_response(api_key).model_dump(),
        "grants": [
            {
                "id": str(g.id),
                "resource_id": str(g.resource_id),
                "grantee_type": g.grantee_type,
                "grantee_id": g.grantee_id,
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
                "state": g.state,
            }
            for g in grants
        ],
    }
