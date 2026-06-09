"""Pydantic schemas for /api-keys endpoints. Ported from `backend/api/auth/api_key.py`."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from kernel.scopes import is_special_scope

VALID_TYPES = {"resource", "tool", "prompt"}
VALID_ACTIONS = {"read", "write", "search", "invoke", "delete", "create", "list"}
CONTENT_TYPE_PATTERN = re.compile(r"^([\w\-\+]+|\*)(/([\w\-\+\.\*]+))?$")
SPECIAL_SCOPE_EXAMPLES = {"licensing:entitlement:host_standard"}


def _validate_scope(scope: str) -> None:
    if is_special_scope(scope):
        return
    parts = scope.split(":")
    if len(parts) < 3:
        raise ValueError(
            f"Invalid scope format: '{scope}'. Must be 'type:contentType:action[:anonymous]' "
            f"or a special scope like {SPECIAL_SCOPE_EXAMPLES}"
        )
    scope_type, mime_type, action = parts[0], parts[1], parts[2]
    if scope_type not in VALID_TYPES:
        raise ValueError(
            f"Invalid type in scope '{scope}': '{scope_type}'. Must be one of {VALID_TYPES}"
        )
    if not CONTENT_TYPE_PATTERN.match(mime_type):
        raise ValueError(
            f"Invalid content type in scope '{scope}': '{mime_type}'. "
            "Must be valid content type or wildcard"
        )
    if action not in VALID_ACTIONS:
        raise ValueError(
            f"Invalid action in scope '{scope}': '{action}'. Must be one of {VALID_ACTIONS}"
        )
    if len(parts) >= 4 and parts[3] != "anonymous":
        raise ValueError(
            f"Invalid flag in scope '{scope}': '{parts[3]}'. Must be 'anonymous' or omitted"
        )


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: Optional[List[str]] = None
    resource_filters: Optional[Dict[str, Any]] = None
    client_id: Optional[str] = None
    host_id: Optional[str] = None
    server_id: Optional[str] = None
    agent_id: Optional[str] = None
    display_label: Optional[str] = None
    expires_at: Optional[str] = None

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        for scope in v:
            _validate_scope(scope)
        return v

    @field_validator("resource_filters")
    @classmethod
    def _validate_resource_filters(
        cls, v: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        for resource_type, filter_value in v.items():
            if filter_value != "*" and not isinstance(filter_value, list):
                raise ValueError(
                    f"Invalid filter for '{resource_type}': must be '*' or list of IDs"
                )
            if isinstance(filter_value, list) and not all(
                isinstance(x, str) for x in filter_value
            ):
                raise ValueError(
                    f"Invalid filter for '{resource_type}': all IDs must be strings"
                )
        return v


class APIKeyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    scopes: Optional[List[str]] = None
    resource_filters: Optional[Dict[str, Any]] = None
    client_id: Optional[str] = None
    host_id: Optional[str] = None
    server_id: Optional[str] = None
    agent_id: Optional[str] = None
    display_label: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        for scope in v:
            _validate_scope(scope)
        return v


class APIKeyResponse(BaseModel):
    id: str
    user_id: str
    name: str
    client_id: Optional[str] = None
    host_id: Optional[str] = None
    server_id: Optional[str] = None
    agent_id: Optional[str] = None
    display_label: Optional[str] = None
    issued_by_user_id: Optional[str] = None
    created_from_client_id: Optional[str] = None
    scopes: List[str]
    resource_filters: Dict[str, Any]
    created_time: str
    modified_time: Optional[str] = None
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    is_active: bool


class APIKeyCreateResponse(APIKeyResponse):
    key: str = Field(..., description="Raw API key — store securely, will not be shown again")
