"""Origin OTP service — Postgres-backed.

Ported from Mantle's `services/otp_service.py`. Email send goes through Origin's
`email_service`; person lookup/create uses Origin's `person_service`.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from sqlalchemy.orm import Session

from origin.db import otp_codes as db_otp

logger = logging.getLogger(__name__)

_OTP_EXPIRY_MINUTES = 10
_MAX_ATTEMPTS_PER_CODE = 3
_LOCKOUT_WINDOW_MINUTES = 5
_MAX_FAILED_IN_WINDOW = 5


def _generate_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def _hash_code(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()


def _verify_code_hash(code: str, code_hash: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode(), code_hash.encode())
    except Exception:
        return False


async def request_otp(db: Session, email: str) -> bool:
    from origin.services import email_service

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_LOCKOUT_WINDOW_MINUTES)
    recent_failed = db_otp.count_recent_failed(db, email, cutoff, _MAX_ATTEMPTS_PER_CODE)
    if recent_failed >= _MAX_FAILED_IN_WINDOW:
        logger.warning("OTP rate limit exceeded for %s", email)
        return False

    code = _generate_code()
    db_otp.create(
        db,
        {
            "email": email,
            "code_hash": _hash_code(code),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=_OTP_EXPIRY_MINUTES),
            "attempts": 0,
            "used": False,
        },
    )
    db.commit()

    sent = await email_service.send_otp(email, code)
    if not sent:
        logger.warning("Failed to send OTP email to %s", email)
        return False
    logger.info("OTP sent to %s", email)
    return True


def verify_otp(db: Session, email: str, code: str) -> Optional[str]:
    """Verify an OTP code. Returns person_id on success.

    Auto-creates the person when the email is unknown — mirrors the OIDC
    auto-create flow so OTP login works for first-time users.
    """
    candidates = db_otp.list_valid_for_email(db, email, _MAX_ATTEMPTS_PER_CODE)
    for otp in candidates:
        db_otp.increment_attempts(db, otp.id)
        if _verify_code_hash(code, otp.code_hash):
            db_otp.mark_used(db, otp.id)
            from origin.services.person_service import get_or_create_user_by_email

            try:
                person = get_or_create_user_by_email(db, email)
            except (ValueError, PermissionError) as exc:
                logger.warning(
                    "OTP verified but person creation denied for %s: %s", email, exc
                )
                db.rollback()
                return None
            db.commit()
            logger.info("OTP verified for %s", email)
            return str(person.id)
    db.commit()
    logger.warning("OTP verification failed for %s", email)
    return None


def cleanup_expired(db: Session) -> int:
    count = db_otp.delete_expired(db)
    db.commit()
    return count
