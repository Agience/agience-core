"""
routers/passkey_router.py

WebAuthn passkey registration and authentication endpoints.

Registration requires an authenticated user (you add a passkey to your account).
Authentication is unauthenticated (you use a passkey to log in).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from arango.database import StandardDatabase

from core.dependencies import get_arango_db
from services.dependencies import get_auth, AuthContext
from services import passkey_service
from services.auth_service import create_jwt_token
from db import arango_identity as arango_ws

logger = logging.getLogger(__name__)

passkey_router = APIRouter(prefix="/auth/passkey", tags=["Authentication"])

# In-memory challenge store (short-lived, per-session)
# In production, use Redis or a DB table. For now, dict is fine for single-instance.
_pending_challenges: dict[str, bytes] = {}


class RegisterOptionsResponse(BaseModel):
    options: dict


class RegisterCompleteRequest(BaseModel):
    credential: dict
    device_name: Optional[str] = None
    challenge: str  # base64url-encoded challenge from registration options


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
    challenge: str  # base64url-encoded challenge from login options
    user_id: str    # from _user_id in login options


class LoginCompleteResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class CredentialListResponse(BaseModel):
    credentials: list[dict]


# ---------------------------------------------------------------------------
#  Registration (requires auth)
# ---------------------------------------------------------------------------

@passkey_router.post("/register-options", response_model=RegisterOptionsResponse)
async def get_register_options(
    auth: AuthContext = Depends(get_auth),
    db: StandardDatabase = Depends(get_arango_db),
):
    """Get WebAuthn registration options for the current user."""
    person = arango_ws.get_person_by_id(db, auth.user_id)
    if not person:
        raise HTTPException(status_code=404, detail="User not found")

    options = passkey_service.get_registration_options(db, auth.user_id, person["email"])
    return RegisterOptionsResponse(options=options)


@passkey_router.post("/register-complete", response_model=RegisterCompleteResponse)
async def complete_registration(
    body: RegisterCompleteRequest,
    auth: AuthContext = Depends(get_auth),
    db: StandardDatabase = Depends(get_arango_db),
):
    """Complete WebAuthn registration — stores the credential."""
    challenge_bytes = passkey_service._b64url_decode(body.challenge)

    result = passkey_service.verify_registration(
        db=db,
        user_id=auth.user_id,
        credential=body.credential,
        expected_challenge=challenge_bytes,
        device_name=body.device_name,
    )
    return RegisterCompleteResponse(**result)


# ---------------------------------------------------------------------------
#  Authentication (no auth required)
# ---------------------------------------------------------------------------

@passkey_router.post("/login-options", response_model=LoginOptionsResponse)
async def get_login_options(
    body: LoginOptionsRequest,
    db: StandardDatabase = Depends(get_arango_db),
):
    """Get WebAuthn authentication options for an email address."""
    has = passkey_service.has_passkeys(db, body.email)
    if not has:
        return LoginOptionsResponse(has_passkeys=False)

    options = passkey_service.get_authentication_options(db, body.email)
    return LoginOptionsResponse(options=options, has_passkeys=True)


@passkey_router.post("/login-complete", response_model=LoginCompleteResponse)
async def complete_login(
    body: LoginCompleteRequest,
    db: StandardDatabase = Depends(get_arango_db),
):
    """Complete WebAuthn authentication — returns JWT tokens."""
    from core import config

    challenge_bytes = passkey_service._b64url_decode(body.challenge)

    person_id = passkey_service.verify_authentication(
        db=db,
        credential=body.credential,
        expected_challenge=challenge_bytes,
        expected_user_id=body.user_id,
    )

    if not person_id:
        raise HTTPException(status_code=401, detail="Passkey authentication failed")

    # Look up person for token claims
    person = arango_ws.get_person_by_id(db, person_id)
    if not person:
        raise HTTPException(status_code=401, detail="User not found")

    user_data = {
        "sub": person["id"],
        "email": person.get("email", ""),
        "name": person.get("name", ""),
        "picture": person.get("picture", ""),
        "client_id": config.PLATFORM_CLIENT_ID,
    }
    access_token = create_jwt_token(user_data)

    refresh_payload = {**user_data, "token_type": "refresh"}
    refresh_token = create_jwt_token(refresh_payload, expires_hours=24 * 30)

    return LoginCompleteResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


# ---------------------------------------------------------------------------
#  Management (requires auth)
# ---------------------------------------------------------------------------

@passkey_router.get("/credentials", response_model=CredentialListResponse)
async def list_passkeys(
    auth: AuthContext = Depends(get_auth),
    db: StandardDatabase = Depends(get_arango_db),
):
    """List all passkey credentials for the current user."""
    creds = passkey_service.list_credentials(db, auth.user_id)
    return CredentialListResponse(credentials=creds)


@passkey_router.delete("/credentials/{credential_id}")
async def delete_passkey(
    credential_id: str,
    auth: AuthContext = Depends(get_auth),
    db: StandardDatabase = Depends(get_arango_db),
):
    """Delete a passkey credential."""
    deleted = passkey_service.delete_credential(db, auth.user_id, credential_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"deleted": True}
