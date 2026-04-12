"""Server credentials router -- CRUD for third-party server identity.

Kernel (first-party) servers authenticate via PLATFORM_INTERNAL_SECRET — no
provisioning required. This router is for third-party / external MCP servers
that need an individually provisioned credential.

All endpoints require human JWT authentication. Third-party servers cannot self-register.
"""
from __future__ import annotations

import secrets as _secrets
from datetime import datetime, timezone
from typing import List

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from arango.database import StandardDatabase

from core import config
from core.dependencies import get_arango_db
from services.dependencies import get_auth, AuthContext
from services import auth_service

from pydantic import BaseModel as _BaseModel

from api.auth.server_credential import (
    ServerCredentialCreate,
    ServerCredentialCreateResponse,
    ServerCredentialResponse,
    ServerCredentialRotateResponse,
    ServerCredentialUpdate,
)
from entities.server_credential import ServerCredential
from db.arango import (
    create_server_credential as db_create,
    get_server_credential_by_client_id as db_get_by_client_id,
    get_all_server_credentials as db_get_all,
    update_server_credential as db_update,
    delete_server_credential as db_delete,
    upsert_server_jwk,
)

router = APIRouter(prefix="/server-credentials", tags=["Server Credentials"])

_SECRET_PREFIX = "scs_"
_SECRET_BYTES = 32


def _generate_secret() -> str:
    """Generate a random client_secret with recognizable prefix."""
    return _SECRET_PREFIX + _secrets.token_urlsafe(_SECRET_BYTES)


def _hash_secret(raw: str) -> str:
    """bcrypt hash a client_secret for storage."""
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def _verify_secret(raw: str, hashed: str) -> bool:
    """Constant-time bcrypt verification."""
    return bcrypt.checkpw(raw.encode(), hashed.encode())


def _entity_to_response(entity: ServerCredential) -> ServerCredentialResponse:
    return ServerCredentialResponse(
        id=entity.id,
        client_id=entity.client_id,
        name=entity.name,
        server_id=entity.server_id,
        host_id=entity.host_id,
        authority=entity.authority,
        scopes=entity.scopes,
        resource_filters=entity.resource_filters,
        is_active=entity.is_active,
        created_time=entity.created_time,
        last_used_at=entity.last_used_at,
        last_rotated_at=entity.last_rotated_at,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ServerCredentialCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_server_credential(
    payload: ServerCredentialCreate,
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Register a new server credential. Returns the client_secret once."""
    existing = db_get_by_client_id(db, payload.client_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"client_id '{payload.client_id}' is already registered",
        )

    raw_secret = _generate_secret()
    now = datetime.now(timezone.utc).isoformat()

    entity = ServerCredential(
        client_id=payload.client_id,
        name=payload.name,
        secret_hash=_hash_secret(raw_secret),
        authority=config.AUTHORITY_DOMAIN,
        host_id=payload.host_id,
        server_id=payload.server_id,
        scopes=payload.scopes,
        resource_filters=payload.resource_filters,
        user_id=auth.user_id,
        is_active=True,
        created_time=now,
        modified_time=now,
    )
    db_create(db, entity)

    return ServerCredentialCreateResponse(
        client_id=entity.client_id,
        client_secret=raw_secret,
        name=entity.name,
        server_id=entity.server_id,
        host_id=entity.host_id,
        authority=entity.authority,
        scopes=entity.scopes,
        resource_filters=entity.resource_filters,
        created_time=entity.created_time,
    )


@router.get(
    "",
    response_model=List[ServerCredentialResponse],
)
def list_server_credentials(
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """List all server credentials."""
    entities = db_get_all(db)
    return [_entity_to_response(e) for e in entities]


@router.get(
    "/{client_id}",
    response_model=ServerCredentialResponse,
)
def get_server_credential(
    client_id: str,
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Get a server credential by client_id (no secret returned)."""
    entity = db_get_by_client_id(db, client_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Server credential not found")
    return _entity_to_response(entity)


@router.patch(
    "/{client_id}",
    response_model=ServerCredentialResponse,
)
def update_server_credential(
    client_id: str,
    payload: ServerCredentialUpdate,
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Update scopes, filters, name, or active status."""
    entity = db_get_by_client_id(db, client_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Server credential not found")

    if payload.name is not None:
        entity.name = payload.name
    if payload.scopes is not None:
        entity.scopes = payload.scopes
    if payload.resource_filters is not None:
        entity.resource_filters = payload.resource_filters
    if payload.is_active is not None:
        entity.is_active = payload.is_active
    entity.modified_time = datetime.now(timezone.utc).isoformat()

    db_update(db, entity)
    return _entity_to_response(entity)


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_server_credential_endpoint(
    client_id: str,
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Delete a server credential."""
    entity = db_get_by_client_id(db, client_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Server credential not found")
    db_delete(db, entity.id)


@router.post(
    "/{client_id}/rotate",
    response_model=ServerCredentialRotateResponse,
)
def rotate_server_credential(
    client_id: str,
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Rotate the client_secret. Old secret is immediately invalidated. Returns new secret once."""
    entity = db_get_by_client_id(db, client_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Server credential not found")

    raw_secret = _generate_secret()
    now = datetime.now(timezone.utc).isoformat()

    entity.secret_hash = _hash_secret(raw_secret)
    entity.last_rotated_at = now
    entity.modified_time = now
    db_update(db, entity)

    return ServerCredentialRotateResponse(
        client_id=entity.client_id,
        client_secret=raw_secret,
        last_rotated_at=now,
    )


# ---------------------------------------------------------------------------
# JWK registration
# ---------------------------------------------------------------------------


class _RegisterJwkRequest(_BaseModel):
    public_jwk: dict


@router.put(
    "/{client_id}/key",
    status_code=status.HTTP_204_NO_CONTENT,
)
def register_server_jwk(
    client_id: str,
    payload: _RegisterJwkRequest,
    request: Request,
    db: StandardDatabase = Depends(get_arango_db),
):
    """Register or update a server's RSA public JWK.

    Only the server identified by `client_id` may register its own key.
    The server presents its platform JWT (obtained via client_credentials
    grant) � `client_id` in the path must match the `client_id` claim
    in the token so servers cannot register keys on behalf of other servers.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = auth_header[7:].strip()
    claims = auth_service.verify_token(token)
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    token_principal_type = claims.get("principal_type", "user")
    token_client_id = claims.get("client_id") or claims.get("sub", "")
    # For server tokens, principal_type == "server" and client_id is set.
    # Also accept builtin servers whose sub is "server/<client_id>".
    if token_principal_type == "server":
        matched = token_client_id == client_id
    else:
        # sub pattern used by builtin kernel server JWTs
        sub = claims.get("sub", "")
        matched = sub == f"server/{client_id}" or sub == client_id
    if not matched:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="client_id mismatch")

    upsert_server_jwk(db, client_id, payload.public_jwk)
