"""Postgres CRUD for `platform_settings`."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from origin.models.platform_setting import PlatformSetting


def get(db: Session, key: str) -> Optional[PlatformSetting]:
    return db.get(PlatformSetting, key)


def set_value(
    db: Session,
    key: str,
    *,
    value: Optional[str] = None,
    secret_value: Optional[str] = None,
    is_secret: bool = False,
    category: Optional[str] = None,
    updated_by: Optional[Union[str, uuid.UUID]] = None,
) -> PlatformSetting:
    setting = db.get(PlatformSetting, key)
    if setting is None:
        setting = PlatformSetting(key=key)
        db.add(setting)
    setting.value = value
    setting.secret_value = secret_value
    setting.is_secret = is_secret
    if category is not None:
        setting.category = category
    if updated_by is not None:
        setting.updated_by = updated_by if isinstance(updated_by, uuid.UUID) else uuid.UUID(updated_by)
    setting.updated_time = datetime.now(timezone.utc)
    db.flush()
    return setting


def list_all(db: Session) -> list[PlatformSetting]:
    return list(db.execute(select(PlatformSetting)).scalars())


def list_by_category(db: Session, category: str) -> list[PlatformSetting]:
    return list(
        db.execute(select(PlatformSetting).where(PlatformSetting.category == category)).scalars()
    )
