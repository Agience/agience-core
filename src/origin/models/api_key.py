"""ApiKey — replaces the Arango `api_keys` collection.

`scopes` is stored as JSON (a list of strings). `resource_filters` is JSON.
`key_hash` is SHA-256 hex (the raw key never stored).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Uuid

from origin.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(
        Uuid,
        ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(256), nullable=False)
    display_label = Column(String(256), nullable=True)
    client_id = Column(String(256), nullable=True, index=True)
    host_id = Column(Uuid, nullable=True)
    server_id = Column(Uuid, nullable=True)
    agent_id = Column(Uuid, nullable=True)
    issued_by_user_id = Column(Uuid, nullable=True)
    created_from_client_id = Column(String(256), nullable=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    requires_nonce = Column(Boolean, nullable=False, default=False)
    scopes = Column(JSON, nullable=False, default=list)
    resource_filters = Column(JSON, nullable=False, default=dict)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    modified_time = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
