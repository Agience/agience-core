from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timezone
import uuid

from core.dependencies import get_arango_db
from services.dependencies import get_auth, AuthContext, get_end_user_claims
from api.auth.api_key import (
    APIKeyResponse,
    APIKeyCreate,
    APIKeyUpdate,
    APIKeyCreateResponse,
)
from entities.api_key import APIKey as APIKeyEntity
from db import arango as arango_db_module
from services import auth_service as auth_svc

router = APIRouter(prefix="/api-keys", tags=["API Keys"])

DEFAULT_SCOPES = [
    "resource:*:read",
    "resource:*:search",
    "resource:*:list",
    "resource:*:invoke",
]

DEFAULT_RESOURCE_FILTERS: Dict[str, Any] = {
    "workspaces": "*",
    "collections": "*",
}



@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    payload: APIKeyCreate,
    arango_db=Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
    user_claims: Dict[str, Any] = Depends(get_end_user_claims),
):
    """Create a new API key for the authenticated user.

    API keys cannot be created by other API keys (JWT only).
    Returns the raw key ONCE - must be stored by the client.
    If scopes/resource_filters are omitted, server applies broad read-oriented defaults.
    """
    # Generate raw key and hash
    raw_key = auth_svc.generate_api_key()
    key_hash = auth_svc.hash_api_key(raw_key)

    resolved_scopes = payload.scopes or list(DEFAULT_SCOPES)
    resolved_filters = payload.resource_filters if payload.resource_filters is not None else dict(DEFAULT_RESOURCE_FILTERS)
    resolved_client_id = payload.client_id or (str(user_claims.get("client_id")) if user_claims.get("client_id") else None)
    resolved_display_label = payload.display_label or "Easy MCP Key"
    
    # Create entity
    now = datetime.now(timezone.utc).isoformat()
    entity = APIKeyEntity(
        id=str(uuid.uuid4()),
        user_id=auth.user_id,
        key_hash=key_hash,
        name=payload.name,
        client_id=resolved_client_id,
        host_id=payload.host_id,
        server_id=payload.server_id,
        agent_id=payload.agent_id,
        display_label=resolved_display_label,
        issued_by_user_id=auth.user_id,
        created_from_client_id=str(user_claims.get("client_id")) if user_claims.get("client_id") else None,
        scopes=resolved_scopes,
        resource_filters=resolved_filters,
        created_time=now,
        modified_time=now,
        expires_at=payload.expires_at,
        last_used_at=None,
        is_active=True,
    )
    
    # Save to database
    created = arango_db_module.create_api_key(arango_db, entity)
    
    # Return with raw key (only time it's exposed)
    return APIKeyCreateResponse(
        id=created.id,
        user_id=created.user_id,
        name=created.name,
        client_id=getattr(created, "client_id", None),
        host_id=getattr(created, "host_id", None),
        server_id=getattr(created, "server_id", None),
        agent_id=getattr(created, "agent_id", None),
        display_label=getattr(created, "display_label", None),
        issued_by_user_id=getattr(created, "issued_by_user_id", None),
        created_from_client_id=getattr(created, "created_from_client_id", None),
        scopes=created.scopes,
        resource_filters=created.resource_filters,
        created_time=created.created_time,
        modified_time=created.modified_time,
        expires_at=created.expires_at,
        last_used_at=created.last_used_at,
        is_active=created.is_active,
        key=raw_key,  # Only returned on creation
    )


@router.get(
    "",
    response_model=List[APIKeyResponse],
    status_code=status.HTTP_200_OK,
)
async def list_api_keys(
    arango_db=Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """List all API keys for the authenticated user.

    Returns metadata only (no secrets).
    """
    keys = arango_db_module.get_api_keys_by_user(arango_db, auth.user_id)
    return [
        APIKeyResponse(
            id=k.id,
            user_id=k.user_id,
            name=k.name,
            client_id=getattr(k, "client_id", None),
            host_id=getattr(k, "host_id", None),
            server_id=getattr(k, "server_id", None),
            agent_id=getattr(k, "agent_id", None),
            display_label=getattr(k, "display_label", None),
            issued_by_user_id=getattr(k, "issued_by_user_id", None),
            created_from_client_id=getattr(k, "created_from_client_id", None),
            scopes=k.scopes,
            resource_filters=k.resource_filters,
            created_time=k.created_time,
            modified_time=k.modified_time,
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
            is_active=k.is_active,
        )
        for k in keys
    ]


@router.get(
    "/{key_id}",
    response_model=APIKeyResponse,
    status_code=status.HTTP_200_OK,
)
async def get_api_key(
    key_id: str,
    arango_db=Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Get a specific API key by ID.

    Only returns keys owned by the authenticated user.
    """
    key = arango_db_module.get_api_key_by_id(arango_db, key_id)

    if not key or key.user_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return APIKeyResponse(
        id=key.id,
        user_id=key.user_id,
        name=key.name,
        client_id=getattr(key, "client_id", None),
        host_id=getattr(key, "host_id", None),
        server_id=getattr(key, "server_id", None),
        agent_id=getattr(key, "agent_id", None),
        display_label=getattr(key, "display_label", None),
        issued_by_user_id=getattr(key, "issued_by_user_id", None),
        created_from_client_id=getattr(key, "created_from_client_id", None),
        scopes=key.scopes,
        resource_filters=key.resource_filters,
        created_time=key.created_time,
        modified_time=key.modified_time,
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        is_active=key.is_active,
    )


@router.patch(
    "/{key_id}",
    response_model=APIKeyResponse,
    status_code=status.HTTP_200_OK,
)
async def update_api_key(
    key_id: str,
    payload: APIKeyUpdate,
    arango_db=Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Update an existing API key.

    Can update name, scopes, resource_filters, and is_active. Only JWT auth allowed.
    """
    key = arango_db_module.get_api_key_by_id(arango_db, key_id)

    if not key or key.user_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Update fields
    if payload.name is not None:
        key.name = payload.name
    if payload.scopes is not None:
        key.scopes = payload.scopes
    if payload.resource_filters is not None:
        key.resource_filters = payload.resource_filters
    if payload.client_id is not None:
        key.client_id = payload.client_id
    if payload.host_id is not None:
        key.host_id = payload.host_id
    if payload.server_id is not None:
        key.server_id = payload.server_id
    if payload.agent_id is not None:
        key.agent_id = payload.agent_id
    if payload.display_label is not None:
        key.display_label = payload.display_label
    if payload.is_active is not None:
        key.is_active = payload.is_active
    
    key.modified_time = datetime.now(timezone.utc).isoformat()
    
    # Save changes
    updated = arango_db_module.update_api_key(arango_db, key)
    
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update API key"
        )
    
    return APIKeyResponse(
        id=updated.id,
        user_id=updated.user_id,
        name=updated.name,
        client_id=getattr(updated, "client_id", None),
        host_id=getattr(updated, "host_id", None),
        server_id=getattr(updated, "server_id", None),
        agent_id=getattr(updated, "agent_id", None),
        display_label=getattr(updated, "display_label", None),
        issued_by_user_id=getattr(updated, "issued_by_user_id", None),
        created_from_client_id=getattr(updated, "created_from_client_id", None),
        scopes=updated.scopes,
        resource_filters=updated.resource_filters,
        created_time=updated.created_time,
        modified_time=updated.modified_time,
        expires_at=updated.expires_at,
        last_used_at=updated.last_used_at,
        is_active=updated.is_active,
    )


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_api_key(
    key_id: str,
    arango_db=Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Delete an API key.

    Only JWT auth allowed (API keys cannot delete themselves).
    """
    key = arango_db_module.get_api_key_by_id(arango_db, key_id)

    if not key or key.user_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    success = arango_db_module.delete_api_key(arango_db, key_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete API key"
        )
