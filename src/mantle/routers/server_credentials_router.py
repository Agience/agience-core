"""Mantle-side slim — only the server JWK upload endpoint.

CRUD for server credentials moved to Origin in 1.1c. The JWK endpoint stays
here because the JWK is consumed by Mantle's secret encryption flow (encrypts
secrets to a server's RSA public key for delivery).

This file disappears entirely once server JWK storage migrates to Origin
alongside the rest of server-credentials. Tracked as a follow-up.
"""
from __future__ import annotations

import logging

from arango.database import StandardDatabase
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from services.dependencies import get_arango_db
from db.arango import upsert_server_jwk
from services import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/server-credentials", tags=["Server Credentials"])


class _RegisterJwkRequest(BaseModel):
    public_jwk: dict


@router.put("/{client_id}/key", status_code=status.HTTP_204_NO_CONTENT)
def register_server_jwk(
    client_id: str,
    payload: _RegisterJwkRequest,
    request: Request,
    db: StandardDatabase = Depends(get_arango_db),
):
    """Register or update a server's RSA public JWK.

    Only the server identified by `client_id` may register its own key. The
    server presents its platform JWT (from Origin via client_credentials).
    `client_id` in the path must match `client_id` in the token so servers
    cannot register keys on behalf of other servers.
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
    if token_principal_type == "server":
        matched = token_client_id == client_id
    else:
        sub = claims.get("sub", "")
        matched = sub == f"server/{client_id}" or sub == client_id
    if not matched:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="client_id mismatch")

    upsert_server_jwk(db, client_id, payload.public_jwk)
