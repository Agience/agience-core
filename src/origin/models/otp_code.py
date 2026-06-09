"""OtpCode — replaces the Arango `otp_codes` collection.

Email uses `COLLATE NOCASE` so lookups are case-insensitive (equivalent to
the Postgres CITEXT semantics this replaced).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, Uuid

from origin.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    email = Column(String(256, collation="NOCASE"), nullable=False, index=True)
    code_hash = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    used = Column(Boolean, nullable=False, default=False, index=True)
    created_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (Index("ix_otp_codes_email_used_expires", "email", "used", "expires_at"),)
