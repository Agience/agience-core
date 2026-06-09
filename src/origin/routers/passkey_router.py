"""Origin passkey router — WebAuthn registration + authentication.

Ported from Mantle. Postgres-backed via `origin.services.passkey_service`.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from kernel import config
from origin.db import persons as db_persons
from origin.db.session import get_db
from origin.services import passkey_service
from origin.services.auth_service import create_jwt_token
from origin.services.dependencies import AuthContext, get_auth

logger = logging.getLogger(__name__)
passkey_router = APIRouter(prefix="/auth/passkey", tags=["Authentication"])


class RegisterOptionsResponse(BaseModel):
    options: dict


class RegisterCompleteRequest(BaseModel):
    credential: dict
    device_name: Optional[str] = None
    challenge: str


class RegisterCompleteResponse(BaseModel):
    credential_id: str
    device_name: Optional[str] = None


class LoginOptionsRequest(BaseModel):
    email: str


class LoginOptionsResponse(BaseModel):
    options: Optional[dict] = None
    has_passkeys: bool = False


class LoginCompleteRequest(BaseModel):
    credential: dict
    challenge: str
    user_id: str


class LoginCompleteResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class CredentialListResponse(BaseModel):
    credentials: list[dict]


# ---------------------------------------------------------------------------
# Registration (requires auth)
# ---------------------------------------------------------------------------
@passkey_router.post("/register-options", response_model=RegisterOptionsResponse)
async def get_register_options(
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    person = db_persons.get_by_id(db, auth.user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="User not found")
    options = passkey_service.get_registration_options(db, str(person.id), person.email or "")
    return RegisterOptionsResponse(options=options)


@passkey_router.post("/register-complete", response_model=RegisterCompleteResponse)
async def complete_registration(
    body: RegisterCompleteRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    challenge_bytes = passkey_service._b64url_decode(body.challenge)
    result = passkey_service.verify_registration(
        db=db,
        user_id=auth.user_id,
        credential=body.credential,
        expected_challenge=challenge_bytes,
        device_name=body.device_name,
    )
    db.commit()
    return RegisterCompleteResponse(**result)


# ---------------------------------------------------------------------------
# Authentication (no auth required)
# ---------------------------------------------------------------------------
@passkey_router.post("/login-options", response_model=LoginOptionsResponse)
async def get_login_options(
    body: LoginOptionsRequest,
    db: Session = Depends(get_db),
):
    has = passkey_service.has_passkeys(db, body.email)
    if not has:
        return LoginOptionsResponse(has_passkeys=False)
    options = passkey_service.get_authentication_options(db, body.email)
    return LoginOptionsResponse(options=options, has_passkeys=True)


@passkey_router.post("/login-complete", response_model=LoginCompleteResponse)
async def complete_login(
    body: LoginCompleteRequest,
    db: Session = Depends(get_db),
):
    challenge_bytes = passkey_service._b64url_decode(body.challenge)
    person_id = passkey_service.verify_authentication(
        db=db,
        credential=body.credential,
        expected_challenge=challenge_bytes,
        expected_user_id=body.user_id,
    )
    if not person_id:
        raise HTTPException(status_code=401, detail="Passkey authentication failed")

    person = db_persons.get_by_id(db, person_id)
    if person is None:
        raise HTTPException(status_code=401, detail="User not found")

    user_data = {
        "sub": str(person.id),
        "email": person.email or "",
        "name": person.name or "",
        "picture": person.picture or "",
        "client_id": getattr(config, "PLATFORM_CLIENT_ID", "platform"),
        "aud": config.AUTHORITY_ISSUER,
    }
    access_token = create_jwt_token(user_data)
    refresh_token = create_jwt_token({**user_data, "token_type": "refresh"}, expires_hours=24 * 30)
    db.commit()
    return LoginCompleteResponse(access_token=access_token, refresh_token=refresh_token)


# ---------------------------------------------------------------------------
# Management (requires auth)
# ---------------------------------------------------------------------------
@passkey_router.get("/credentials", response_model=CredentialListResponse)
async def list_passkeys(
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    creds = passkey_service.list_credentials(db, auth.user_id)
    return CredentialListResponse(credentials=creds)


@passkey_router.delete("/credentials/{credential_id}")
async def delete_passkey(
    credential_id: str,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    deleted = passkey_service.delete_credential(db, auth.user_id, credential_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")
    db.commit()
    return {"deleted": True}
