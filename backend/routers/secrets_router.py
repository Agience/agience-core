"""
Secrets Router -- generic encrypted credential management.

Endpoints:
    GET    /secrets             List stored secrets (filter by ?type= and/or ?provider=)
    POST   /secrets             Store a new secret
    DELETE /secrets/{id}        Delete a secret
    POST   /secrets/{id}/set-default  Mark a secret as the default for its (type, provider)
    POST   /secrets/fetch            Return a secret wrapped as JWE for a delegated server

Secret types:
    llm_key         -- BYOK keys for OpenAI, Anthropic, Azure, etc.
    github_token    -- GitHub OAuth / PAT for Copilot and GitHub API access
    integration_key -- Any other third-party integration credential
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from arango.database import StandardDatabase

from core.dependencies import get_arango_db
from services.dependencies import get_auth, AuthContext
from services import secrets_service, auth_service
from db.arango import get_server_jwk
from api.secrets import SecretResponse, SecretFetchRequest, SecretFetchResponse, SecretCreateRequest

router = APIRouter(prefix="/secrets", tags=["Secrets"])


def _to_response(s: secrets_service.SecretConfig, include_encrypted: bool = False) -> SecretResponse:
    resp = SecretResponse(
        id=s.id,
        type=s.type,
        provider=s.provider,
        label=s.label,
        created_time=s.created_time,
        is_default=s.is_default,
        authorizer_id=s.authorizer_id or None,
        expires_at=s.expires_at or None,
    )
    if include_encrypted:
        resp.encrypted_value = s.encrypted_value
    return resp


@router.get("", response_model=List[SecretResponse])
def list_secrets(
    type: Optional[str] = Query(None, description="Filter by secret type"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    id: Optional[str] = Query(None, description="Filter by exact secret ID"),
    authorizer_id: Optional[str] = Query(None, description="Filter by authorizer artifact ID"),
    include_encrypted: bool = Query(False, description="Include encrypted_value in response"),
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """List stored secrets. Encrypted values only returned when include_encrypted=True."""
    secrets = secrets_service.list_secrets(
        db, auth.user_id,
        secret_type=type,
        provider=provider,
        secret_id=id,
        authorizer_id=authorizer_id,
    )
    return [_to_response(s, include_encrypted=include_encrypted) for s in secrets]


@router.post("", response_model=List[SecretResponse], status_code=status.HTTP_201_CREATED)
def add_secret(
    payload: SecretCreateRequest,
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Store a new secret (value encrypted before storage). Returns all secrets."""
    secrets = secrets_service.add_secret(
        db,
        auth.user_id,
        secret_type=payload.type,
        provider=payload.provider,
        label=payload.label,
        value=payload.value,
        is_default=payload.is_default,
        authorizer_id=payload.authorizer_id or "",
        expires_at=payload.expires_at or "",
    )
    return [_to_response(s) for s in secrets]


@router.delete("/{secret_id}", response_model=List[SecretResponse])
def delete_secret(
    secret_id: str,
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Delete a stored secret. Returns remaining secrets."""
    secrets = secrets_service.delete_secret(db, auth.user_id, secret_id)
    return [_to_response(s) for s in secrets]


@router.post("/{secret_id}/set-default", response_model=List[SecretResponse])
def set_default_secret(
    secret_id: str,
    db: StandardDatabase = Depends(get_arango_db),
    auth: AuthContext = Depends(get_auth),
):
    """Mark a secret as the default for its (type, provider) combination."""
    secrets = secrets_service.set_default_secret(db, auth.user_id, secret_id)
    return [_to_response(s) for s in secrets]


@router.post("/fetch", response_model=SecretFetchResponse)
def fetch_secret_for_server(
    payload: SecretFetchRequest,
    request: Request,
    db: StandardDatabase = Depends(get_arango_db),
):
    """Return a secret wrapped as JWE for the requesting server.

    Auth: The caller must present a **delegation JWT** (RFC 8693) issued by
    Core.  ``sub`` is the user whose secret is being fetched; ``act.sub`` is
    the ``client_id`` of the server requesting the secret.  The JWE envelope
    is encrypted with the server's registered RSA public key so only that
    server can decrypt it.  Plaintext never leaves Core unencrypted.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = auth_header[7:].strip()
    claims = auth_service.verify_token(token)
    if not claims or claims.get("principal_type") != "delegation":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Delegation JWT required")

    user_id: str = claims["sub"]
    server_client_id: str = claims.get("act", {}).get("sub", "")
    if not server_client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="act.sub missing from delegation JWT")

    # The aud claim must match act.sub — proving this token was issued TO the
    # server that is presenting it, not re-used from a different delegation.
    if claims.get("aud") != server_client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token audience does not match presenter")

    public_jwk = get_server_jwk(db, server_client_id)
    if not public_jwk:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No public key registered for server")

    secrets = secrets_service.list_secrets(
        db, user_id,
        secret_type=payload.type,
        provider=payload.provider,
        secret_id=payload.secret_id,
        authorizer_id=payload.authorizer_id,
    )
    if not secrets:
        raise HTTPException(status_code=404, detail="Secret not found")

    secret = secrets[0]
    plaintext = secrets_service.decrypt_value(secret.encrypted_value)
    jwe = secrets_service.wrap_secret_for_server(plaintext, public_jwk)

    return SecretFetchResponse(id=secret.id, type=secret.type, jwe=jwe)
