"""Origin's auth dependency layer.

Mirrors the shape of mantle's `services/dependencies.py` but reads from
Postgres. The `AuthContext` returned here is functionally equivalent — same
field names, same principal types — so router code is portable across the
two processes.

`grants` on AuthContext holds Origin SQLAlchemy `Grant` rows (not Arango
GrantEntity). Routers in Origin work with these directly. Cross-service
checks (mantle → Origin grant-check) come in 1.2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import OAuth2AuthorizationCodeBearer
from sqlalchemy.orm import Session

from kernel import config
from origin.db import grants as db_grants
from origin.db.session import get_db
from origin.models.api_key import ApiKey as ApiKeyModel
from origin.models.grant import Grant as GrantModel
from origin.models.person import Person as PersonModel
from origin.services import person_service
from origin.services.auth_verifier import verify_api_key, verify_token

logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    """Unified auth context. Field names match mantle's AuthContext for parity."""

    principal_id: str = ""
    principal_type: str = "user"            # user | api_key | server | mcp_client | grant_key | delegation
    user_id: Optional[str] = None
    grants: List[GrantModel] = field(default_factory=list)
    api_key_id: Optional[str] = None
    api_key_entity: Optional[ApiKeyModel] = None
    server_id: Optional[str] = None
    actor: Optional[str] = None
    authority: Optional[str] = None
    host_id: Optional[str] = None
    bearer_grant: Optional[GrantModel] = None
    target_artifact_id: Optional[str] = None


oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl="/auth/authorize",
    tokenUrl="/auth/token",
)


def _is_api_key_jwt(payload: Optional[dict]) -> bool:
    return bool(payload and payload.get("api_key_id"))


def _validate_aud_for_principal(payload: dict) -> None:
    principal_type = payload.get("principal_type", "user")
    aud = payload.get("aud")
    if principal_type == "service":
        # Phase C kernel mutual JWT: kernel callers (mantle, Chorus) sign their
        # own tokens with `aud="origin"` when calling into Origin.
        if aud != "origin":
            raise HTTPException(status_code=401, detail="Invalid token audience for kernel service")
    elif principal_type == "server":
        if aud != "agience":
            raise HTTPException(status_code=401, detail="Invalid token audience for server credential")
    elif principal_type == "mcp_client":
        if not aud:
            raise HTTPException(status_code=401, detail="Missing aud in mcp_client token")
    elif principal_type == "delegation":
        if not aud:
            raise HTTPException(status_code=401, detail="Missing aud in delegation token")
    else:
        if aud != config.AUTHORITY_ISSUER:
            raise HTTPException(status_code=401, detail="Invalid token audience")


def resolve_auth(token: str, db: Session, request: Optional[Request] = None) -> AuthContext:
    """Origin's token dispatch — Postgres-backed.

    Same shape as mantle's `resolve_auth` but talks to Origin's tables.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    raw_token = token.strip()
    target_artifact_id: Optional[str] = None

    # {artifact_id}:agc_xxx prefix
    if ":" in raw_token and not raw_token.startswith("ey"):
        parts = raw_token.split(":", 1)
        if len(parts) == 2 and parts[1].startswith("agc_"):
            target_artifact_id = parts[0]
            raw_token = parts[1]

    # API key
    if raw_token.startswith("agc_"):
        api_key = verify_api_key(db, raw_token)
        if api_key is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        grants = db_grants.get_active_for_grantee(db, str(api_key.id), "api_key")
        return AuthContext(
            principal_id=str(api_key.id),
            principal_type="api_key",
            user_id=str(api_key.user_id) if api_key.user_id else None,
            grants=grants,
            api_key_id=str(api_key.id),
            api_key_entity=api_key,
            target_artifact_id=target_artifact_id,
        )

    # JWT
    payload = verify_token(raw_token)
    if payload and "sub" in payload:
        _validate_aud_for_principal(payload)
        if _is_api_key_jwt(payload):
            raise HTTPException(status_code=403, detail="API-key JWT not accepted; use direct API key")

        jwt_principal_type = payload.get("principal_type", "user")
        if jwt_principal_type == "service":
            # Phase C kernel mutual JWT — mantle/chorus identifying themselves
            # to Origin. `iss` carries the service name (already verified as
            # one of {"mantle", "chorus"} by `verify_token`).
            return AuthContext(
                principal_id=str(payload.get("iss", "")),
                principal_type="service",
                authority=str(payload.get("iss", "")) or None,
            )
        if jwt_principal_type == "server":
            client_id = payload.get("client_id")
            return AuthContext(
                principal_id=str(client_id) if client_id else str(payload.get("sub", "")),
                principal_type="server",
                server_id=str(payload.get("server_id")) if payload.get("server_id") else None,
                authority=str(payload.get("authority", "")) or None,
                host_id=str(payload.get("host_id", "")) or None,
            )
        if jwt_principal_type == "mcp_client":
            return AuthContext(
                principal_id=str(payload.get("aud", "")),
                principal_type="mcp_client",
                user_id=str(payload.get("sub")) if payload.get("sub") else None,
            )
        if jwt_principal_type == "delegation":
            d_sub = payload.get("sub")
            d_act = (payload.get("act") or {}).get("sub")
            if not d_sub:
                raise HTTPException(status_code=401, detail="Delegation token missing sub")
            if not d_act:
                raise HTTPException(status_code=401, detail="Delegation token missing act.sub")
            return AuthContext(
                principal_id=str(d_sub),
                principal_type="user",
                user_id=str(d_sub),
                actor=str(d_act),
                authority=str(payload.get("iss", "")) or None,
                host_id=str(payload.get("host_id", "")) or None,
            )

        # Default: user JWT
        user_id = str(payload.get("sub")) if payload.get("sub") else None
        return AuthContext(
            principal_id=user_id or "",
            principal_type="user",
            user_id=user_id,
        )

    # Grant key in Bearer slot
    key_grants = db_grants.get_active_by_key(db, raw_token)
    if key_grants:
        grant = key_grants[0]
        return AuthContext(
            principal_id=str(grant.id),
            principal_type="grant_key",
            grants=[grant],
            bearer_grant=grant,
        )

    raise HTTPException(status_code=401, detail="Invalid token")


async def get_auth(
    token: str = Security(oauth2_scheme),
    db: Session = Depends(get_db),
    request: Request = None,
) -> AuthContext:
    auth = resolve_auth(token=token or "", db=db, request=request)
    if request is not None and auth.user_id:
        request.state.user_id = auth.user_id
    return auth


async def get_person(
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> PersonModel:
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="User identification required")
    person = person_service.get_user_by_id(db, auth.user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="User not found")
    return person
