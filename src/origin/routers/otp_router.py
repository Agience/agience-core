"""Origin OTP router — email one-time-password login.

Ported from Mantle. Postgres-backed via `origin.services.otp_service`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from kernel import config
from origin.db import persons as db_persons
from origin.db.session import get_db
from origin.services import email_service, otp_service
from origin.services.auth_service import create_jwt_token

logger = logging.getLogger(__name__)
otp_router = APIRouter(prefix="/auth/otp", tags=["Authentication"])


class OTPRequestBody(BaseModel):
    email: str


class OTPRequestResponse(BaseModel):
    sent: bool
    expires_in: int = 600


class OTPVerifyBody(BaseModel):
    email: str
    code: str


class OTPVerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@otp_router.post("/request", response_model=OTPRequestResponse)
async def request_otp(
    body: OTPRequestBody,
    db: Session = Depends(get_db),
):
    if not email_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Use password login instead.",
        )

    person = db_persons.get_by_email(db, body.email)
    if person is None:
        # Don't reveal whether the email exists.
        logger.info("OTP requested for unknown email: %s", body.email)
        return OTPRequestResponse(sent=True)

    sent = await otp_service.request_otp(db, body.email)
    if not sent:
        raise HTTPException(
            status_code=429, detail="Too many attempts. Please try again later."
        )
    return OTPRequestResponse(sent=True)


@otp_router.post("/verify", response_model=OTPVerifyResponse)
async def verify_otp(
    body: OTPVerifyBody,
    db: Session = Depends(get_db),
):
    person_id = otp_service.verify_otp(db, body.email, body.code)
    if not person_id:
        raise HTTPException(status_code=401, detail="Invalid or expired code")

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
    return OTPVerifyResponse(access_token=access_token, refresh_token=refresh_token)
