"""API schemas for platform admin endpoints."""

from typing import List, Optional

from pydantic import BaseModel


class PlatformUserResponse(BaseModel):
    """A user with their platform-admin status."""
    id: str
    email: str
    name: str
    picture: Optional[str] = None
    is_platform_admin: bool
    created_time: Optional[str] = None


class PlatformUsersListResponse(BaseModel):
    users: List[PlatformUserResponse]


class SeedCollectionResponse(BaseModel):
    """Metadata for a platform seed collection."""
    id: str
    name: str
    description: Optional[str] = None
    artifact_count: int = 0
