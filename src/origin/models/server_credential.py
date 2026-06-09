"""ServerCredential — replaces the Arango `server_credentials` collection.

Kernel servers authenticate via OAuth 2.0 client_credentials grant. Each server
has a well-known client_id and a bcrypt-hashed client_secret.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Text, Uuid

from origin.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ServerCredential(Base):
    __tablename__ = "server_credentials"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id = Column(String(256), nullable=False, unique=True, index=True)
    name = Column(String(256), nullable=False)
    secret_hash = Column(Text, nullable=False)
    authority = Column(String(256), nullable=False)
    host_id = Column(Uuid, nullable=False)
    server_id = Column(Uuid, nullable=False)
    user_id = Column(Uuid, ForeignKey("persons.id"), nullable=False)
    scopes = Column(JSON, nullable=False, default=list)
    resource_filters = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_rotated_at = Column(DateTime(timezone=True), nullable=True)
    created_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    modified_time = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
