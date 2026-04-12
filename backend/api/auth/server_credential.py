from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ServerCredentialCreate(BaseModel):
    """Register a new server credential."""
    client_id: str = Field(description="Well-known server identifier (e.g. agience-server-seraph)")
    name: str = Field(description="Human-readable label (e.g. seraph @ aria.ikailo.com)")
    server_id: str = Field(description="Which code (e.g. seraph)")
    host_id: str = Field(description="Which compute (e.g. aria.ikailo.com)")
    scopes: List[str] = Field(default=["tool:*:invoke", "resource:*:read"])
    resource_filters: Dict[str, Any] = Field(default={"workspaces": "*", "collections": "*"})


class ServerCredentialCreateResponse(BaseModel):
    """Returned once after registration -- includes the raw client_secret."""
    client_id: str
    client_secret: str
    name: str
    server_id: str
    host_id: str
    authority: str
    scopes: List[str]
    resource_filters: Dict[str, Any]
    created_time: str


class ServerCredentialResponse(BaseModel):
    """Public view of a server credential (never includes secret)."""
    id: str
    client_id: str
    name: str
    server_id: str
    host_id: str
    authority: str
    scopes: List[str]
    resource_filters: Dict[str, Any]
    is_active: bool
    created_time: str
    last_used_at: Optional[str] = None
    last_rotated_at: Optional[str] = None


class ServerCredentialUpdate(BaseModel):
    """Partial update for a server credential."""
    name: Optional[str] = None
    scopes: Optional[List[str]] = None
    resource_filters: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ServerCredentialRotateResponse(BaseModel):
    """Returned after secret rotation -- includes the new raw client_secret."""
    client_id: str
    client_secret: str
    last_rotated_at: str
