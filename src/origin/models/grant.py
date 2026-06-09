"""Grant — replaces the Arango `grants` collection.

The hot path: `(grantee_id, resource_id, state)` is the primary access lookup.
`resource_id` references artifacts in Mantle's Arango DB and is intentionally
NOT a foreign key — we trade referential integrity for cross-DB independence.

CRUDEASIO permission model: Create, Read, Update, Delete, Evict, Add, Share,
Invoke, Admin.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, Uuid, text

from origin.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Grant(Base):
    __tablename__ = "grants"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    resource_id = Column(Uuid, nullable=False, index=True)
    grantee_type = Column(String(16), nullable=False)
    grantee_id = Column(String(256), nullable=False)
    granted_by = Column(Uuid, nullable=False)
    effect = Column(String(8), nullable=False, default="allow")

    # CRUDEASIO flags
    can_create = Column(Boolean, nullable=False, default=False)
    can_read = Column(Boolean, nullable=False, default=True)
    can_update = Column(Boolean, nullable=False, default=False)
    can_delete = Column(Boolean, nullable=False, default=False)
    can_evict = Column(Boolean, nullable=False, default=False)
    can_invoke = Column(Boolean, nullable=False, default=False)
    can_add = Column(Boolean, nullable=False, default=False)
    can_share = Column(Boolean, nullable=False, default=False)
    can_admin = Column(Boolean, nullable=False, default=False)

    # Identity-required overrides (nullable: inherit from `requires_identity`)
    requires_identity = Column(Boolean, nullable=False, default=False)
    read_requires_identity = Column(Boolean, nullable=True)
    write_requires_identity = Column(Boolean, nullable=True)
    invoke_requires_identity = Column(Boolean, nullable=True)

    # Invite targeting (only used when grantee_type == 'invite')
    target_entity = Column(String(256), nullable=True)
    target_entity_type = Column(String(32), nullable=True)
    max_claims = Column(Integer, nullable=True)
    claims_count = Column(Integer, nullable=False, default=0)

    # Lifecycle
    state = Column(String(16), nullable=False, default="active", index=True)
    name = Column(String(256), nullable=True)
    notes = Column(Text, nullable=True)
    granted_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    accepted_by = Column(Uuid, nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(Uuid, nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    modified_time = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_grants_grantee_resource_state", "grantee_id", "resource_id", "state"),
        Index("ix_grants_grantee_type_id_state", "grantee_type", "grantee_id", "state"),
        Index(
            "ix_grants_resource_active",
            "resource_id",
            "state",
            sqlite_where=text("state = 'active'"),
        ),
    )
