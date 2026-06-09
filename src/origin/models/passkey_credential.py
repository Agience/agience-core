"""PasskeyCredential — replaces the Arango `passkey_credentials` collection.

WebAuthn `credential_id` is variable-length base64url; kept as String PK rather
than UUID. Cascade delete on the owning person.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Uuid,
)

from origin.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"

    id = Column(String(512), primary_key=True)
    person_id = Column(
        Uuid,
        ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(BigInteger, nullable=False, default=0)
    transports = Column(JSON, nullable=True)
    aaguid = Column(String(64), nullable=True)
    device_name = Column(String(128), nullable=True)
    backup_eligible = Column(Boolean, nullable=False, default=False)
    backup_state = Column(Boolean, nullable=False, default=False)
    created_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
