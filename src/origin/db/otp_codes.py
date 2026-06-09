"""Postgres CRUD for `otp_codes`."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import delete as sa_delete, func, select, update as sa_update
from sqlalchemy.orm import Session

from origin.models.otp_code import OtpCode


def create(db: Session, fields: Mapping[str, Any]) -> OtpCode:
    payload = dict(fields)
    if "id" in payload and payload["id"]:
        payload["id"] = _to_uuid(payload["id"])
    else:
        payload["id"] = uuid.uuid4()
    code = OtpCode(**payload)
    db.add(code)
    db.flush()
    return code


def list_valid_for_email(
    db: Session, email: str, max_attempts: int, now: datetime | None = None
) -> list[OtpCode]:
    """Unexpired, unused, attempts < max — sorted newest first."""
    cutoff = now or datetime.now(timezone.utc)
    return list(
        db.execute(
            select(OtpCode)
            .where(
                OtpCode.email == email,
                OtpCode.expires_at > cutoff,
                OtpCode.used.is_(False),
                OtpCode.attempts < max_attempts,
            )
            .order_by(OtpCode.created_time.desc())
        ).scalars()
    )


def increment_attempts(db: Session, otp_id: str | uuid.UUID) -> None:
    db.execute(
        sa_update(OtpCode)
        .where(OtpCode.id == _to_uuid(otp_id))
        .values(attempts=OtpCode.attempts + 1)
    )


def mark_used(db: Session, otp_id: str | uuid.UUID) -> None:
    db.execute(
        sa_update(OtpCode).where(OtpCode.id == _to_uuid(otp_id)).values(used=True)
    )


def count_recent_failed(
    db: Session, email: str, since: datetime, max_attempts: int
) -> int:
    return db.execute(
        select(func.count())
        .select_from(OtpCode)
        .where(
            OtpCode.email == email,
            OtpCode.created_time >= since,
            OtpCode.used.is_(False),
            OtpCode.attempts >= max_attempts,
        )
    ).scalar_one()


def delete_expired(db: Session, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=1)
    result = db.execute(
        sa_delete(OtpCode).where(
            (OtpCode.used.is_(True)) | (OtpCode.expires_at <= cutoff)
        )
    )
    return result.rowcount or 0


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
