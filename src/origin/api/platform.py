"""Pydantic schemas for /platform endpoints (Origin-side)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class PlatformUserResponse(BaseModel):
    id: str
    email: str
    name: str
    picture: Optional[str] = None
    is_platform_admin: bool
    created_time: Optional[str] = None


class PlatformUsersListResponse(BaseModel):
    users: List[PlatformUserResponse]
