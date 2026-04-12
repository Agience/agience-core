# /api/auth/api_key.py

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
import re
from core.scopes import is_special_scope

VALID_TYPES = {"resource", "tool", "prompt"}
VALID_ACTIONS = {"read", "write", "search", "invoke", "delete", "create", "list"}
CONTENT_TYPE_PATTERN = re.compile(r'^([\w\-\+]+|\*)(/([\w\-\+\.\*]+))?$')


SPECIAL_SCOPE_EXAMPLES = {
    "licensing:entitlement:host_standard",
}

class APIKeyCreate(BaseModel):
    """Request model for creating a new API key."""
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable name for the API key")
    scopes: Optional[List[str]] = Field(
        default=None,
        description="Optional scopes in format 'type:contentType:action[:anonymous]'. When omitted, server applies broad read-oriented defaults.",
    )
    resource_filters: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Optional resource access filters (e.g., {\"collections\": [\"col-123\"]})"
    )
    client_id: Optional[str] = Field(default=None, description="Optional presenter client identifier")
    host_id: Optional[str] = Field(default=None, description="Optional host identifier")
    server_id: Optional[str] = Field(default=None, description="Optional server identifier")
    agent_id: Optional[str] = Field(default=None, description="Optional agent identifier")
    display_label: Optional[str] = Field(default=None, description="Optional human-friendly presenter label")
    expires_at: Optional[str] = Field(default=None, description="ISO 8601 expiration timestamp")

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate scope format: type:contentType:action[:anonymous] or special system scopes"""
        if v is None:
            return v

        for scope in v:
            if is_special_scope(scope):
                continue
            
            parts = scope.split(":")
            if len(parts) < 3:
                raise ValueError(
                    f"Invalid scope format: '{scope}'. "
                    f"Must be 'type:contentType:action[:anonymous]' or a special scope like {SPECIAL_SCOPE_EXAMPLES}"
                )
            
            scope_type, mime_type, action = parts[0], parts[1], parts[2]
            
            # Validate type
            if scope_type not in VALID_TYPES:
                raise ValueError(f"Invalid type in scope '{scope}': '{scope_type}'. Must be one of {VALID_TYPES}")
            
            # Validate MIME type
            if not CONTENT_TYPE_PATTERN.match(mime_type):
                raise ValueError(
                    f"Invalid content type in scope '{scope}': '{mime_type}'. "
                    f"Must be valid content type or wildcard (e.g., text/markdown, text/*, *)"
                )
            
            # Validate action
            if action not in VALID_ACTIONS:
                raise ValueError(f"Invalid action in scope '{scope}': '{action}'. Must be one of {VALID_ACTIONS}")
            
            # Validate anonymous flag if present
            if len(parts) >= 4 and parts[3] != "anonymous":
                raise ValueError(f"Invalid flag in scope '{scope}': '{parts[3]}'. Must be 'anonymous' or omitted")
        
        return v

    @field_validator("resource_filters")
    @classmethod
    def validate_resource_filters(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate resource_filters format"""
        if v is None:
            return v
        for resource_type, filter_value in v.items():
            if filter_value != "*" and not isinstance(filter_value, list):
                raise ValueError(f"Invalid filter for '{resource_type}': must be '*' or list of IDs")
            if isinstance(filter_value, list) and not all(isinstance(x, str) for x in filter_value):
                raise ValueError(f"Invalid filter for '{resource_type}': all IDs must be strings")
        return v


class APIKeyUpdate(BaseModel):
    """Request model for updating an existing API key."""
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
    def validate_scopes(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate scope format if provided: type:contentType:action[:anonymous]"""
        if v is None:
            return v
        
        for scope in v:
            if is_special_scope(scope):
                continue

            parts = scope.split(":")
            if len(parts) < 3:
                raise ValueError(
                    f"Invalid scope format: '{scope}'. "
                    f"Must be 'type:contentType:action[:anonymous]' or a supported special scope"
                )
            
            scope_type, mime_type, action = parts[0], parts[1], parts[2]
            
            # Validate type
            if scope_type not in VALID_TYPES:
                raise ValueError(f"Invalid type in scope '{scope}': '{scope_type}'. Must be one of {VALID_TYPES}")
            
            # Validate MIME type
            if not CONTENT_TYPE_PATTERN.match(mime_type):
                raise ValueError(
                    f"Invalid content type in scope '{scope}': '{mime_type}'. "
                    f"Must be valid content type or wildcard"
                )
            
            # Validate action
            if action not in VALID_ACTIONS:
                raise ValueError(f"Invalid action in scope '{scope}': '{action}'. Must be one of {VALID_ACTIONS}")
            
            # Validate anonymous flag if present
            if len(parts) >= 4 and parts[3] != "anonymous":
                raise ValueError(f"Invalid flag in scope '{scope}': '{parts[3]}'. Must be 'anonymous' or omitted")
        
        return v


class APIKeyResponse(BaseModel):
    """Response model for API key (never includes raw key, only on creation)."""
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
    """Response model for API key creation - includes raw key ONCE."""
    key: str = Field(..., description="Raw API key - store securely, will not be shown again")
