"""Person — replaces the Arango `people` collection.

Email and username use `COLLATE NOCASE` so lookups are case-insensitive
(equivalent to the Postgres CITEXT semantics this replaced). OIDC identity
uses a partial unique index where `oidc_provider IS NOT NULL`.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Index, String, Text, Uuid, text

from origin.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Person(Base):
    __tablename__ = "persons"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    email = Column(String(256, collation="NOCASE"), nullable=True, unique=True)
    username = Column(String(256, collation="NOCASE"), nullable=True, unique=True)
    name = Column(String(256), nullable=False, server_default="")
    picture = Column(Text, nullable=True)
    password_hash = Column(Text, nullable=True)
    oidc_provider = Column(String(64), nullable=True)
    oidc_subject = Column(String(256), nullable=True)
    google_id = Column(String(256), nullable=True)
    preferences = Column(JSON, nullable=False, default=dict)
    created_time = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    modified_time = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index(
            "ix_persons_oidc_identity",
            "oidc_provider",
            "oidc_subject",
            unique=True,
            sqlite_where=text("oidc_provider IS NOT NULL"),
        ),
        Index("ix_persons_google_id", "google_id"),
    )
