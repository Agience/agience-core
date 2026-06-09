"""PlatformSetting — replaces the Arango `platform_settings` collection.

`is_secret` discriminates which column carries the value: plain settings use
`value`, secret settings use Fernet-encrypted `secret_value`. Encryption happens
in the service layer.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, Uuid

from origin.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    secret_value = Column(Text, nullable=True)
    is_secret = Column(Boolean, nullable=False, default=False)
    category = Column(String(64), nullable=True, index=True)
    updated_by = Column(Uuid, ForeignKey("persons.id"), nullable=True)
    created_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_time = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
