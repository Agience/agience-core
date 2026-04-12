"""
routers/otp_router.py

Email OTP (one-time password) authentication endpoints.

OTP login is available when email service is configured. It's an alternative
to password auth — user enters email, receives a 6-digit code, enters it.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from arango.database import StandardDatabase

from core.dependencies import get_arango_db
from services import otp_service, email_service
from services.auth_service import create_jwt_token
from db import arango_identity as arango_ws

logger = logging.getLogger(__name__)

otp_router = APIRouter(prefix="/auth/otp", tags=["Authentication"])


class OTPRequestBody(BaseModel):
    email: str


class OTPRequestResponse(BaseModel):
    sent: bool
    expires_in: int = 600  # seconds


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
    db: StandardDatabase = Depends(get_arango_db),
):
    """
    Request an OTP code sent to the given email address.

    Requires email service to be configured. The code expires in 10 minutes.
    Rate-limited: 5 failed attempts per email triggers a 5-minute lockout.
    """
    if not email_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Use password login instead.",
        )

    # Check if the email exists in the system
    person = arango_ws.get_person_by_email(db, body.email)
    if not person:
        # Don't reveal whether the email exists — return success either way
        # but don't actually send anything
        logger.info("OTP requested for unknown email: %s", body.email)
        return OTPRequestResponse(sent=True)

    sent = await otp_service.request_otp(db, body.email)
    if not sent:
        # Could be rate-limited or email send failure
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please try again later.",
        )

    return OTPRequestResponse(sent=True)


@otp_router.post("/verify", response_model=OTPVerifyResponse)
async def verify_otp(
    body: OTPVerifyBody,
    db: StandardDatabase = Depends(get_arango_db),
):
    """
    Verify an OTP code and return JWT tokens.

    The code must match and not be expired. Max 3 attempts per code.
    """
    from core import config

    person_id = otp_service.verify_otp(db, body.email, body.code)
    if not person_id:
        raise HTTPException(status_code=401, detail="Invalid or expired code")

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

    return OTPVerifyResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )
