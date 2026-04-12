# /core/scopes.py

"""
API Key scope verification utilities.

Scope Format: [type]:[contentType]:[action][:anonymous]
Special System Scopes:
- licensing:entitlement:<entitlement_name>

Components:
- Type: resource, tool, prompt (maps to MCP primitives)
- Content Type: Standard content type or wildcard (e.g., text/markdown, text/*, *)
- Action: read, write, search, invoke, delete, create
- Anonymous: Optional :anonymous suffix (default is identified access)

Examples:
- "resource:application/vnd.agience.collection+json:read"
- "resource:text/markdown:write:anonymous"
- "tool:application/vnd.agience.collection+json:search"
- "resource:text/*:read" (wildcard - all text types)
- "tool:*:invoke" (wildcard - all tools)

URI-based Storage:
- Scopes control content type access (what you can do)
- URIs control storage location (where it lives)
- Backend routes by URI scheme: agience://, file://, s3://, https://
"""

import re
from typing import Optional, Tuple
from fastapi import HTTPException, status
from entities.api_key import APIKey as APIKeyEntity

VALID_TYPES = {"resource", "tool", "prompt"}
VALID_ACTIONS = {"read", "write", "search", "invoke", "delete", "create"}
SPECIAL_SCOPES = {
    "collections:commit:verified",
}
LICENSING_SCOPE_PATTERN = re.compile(r"^licensing:entitlement:([a-zA-Z0-9_\-]+)$")

# Content type pattern: type/subtype (supports wildcards and vendor prefixes)
# Examples: text/plain, application/vnd.agience.collection+json, text/*, *
CONTENT_TYPE_PATTERN = re.compile(r'^([\w\-\+]+|\*)(/([\w\-\+\.\*]+))?$')


def is_special_scope(scope_str: str) -> bool:
    """Return True when a scope uses one of the reserved system-level formats."""
    return scope_str in SPECIAL_SCOPES or bool(LICENSING_SCOPE_PATTERN.match(scope_str))


def extract_licensing_entitlements(scopes: list[str]) -> set[str]:
    """Extract entitlement names from explicit licensing scopes."""
    entitlements: set[str] = set()
    for scope in scopes:
        match = LICENSING_SCOPE_PATTERN.match(scope)
        if match:
            entitlements.add(match.group(1))
    return entitlements


def parse_scope(scope_str: str) -> Tuple[str, str, str, bool]:
    """
    Parse a scope string into components.

    Args:
        scope_str: Scope in format "type:contentType:action[:anonymous]"
        Examples:
            "resource:text/markdown:write"
            "resource:text/markdown:write:anonymous"
            "tool:application/vnd.agience.collection+json:search"
            "resource:text/*:read"

    Returns:
        Tuple of (type, content_type, action, is_anonymous)

    Raises:
        ValueError: If scope format is invalid
    """
    if is_special_scope(scope_str):
        raise ValueError(f"Special system scope '{scope_str}' does not use content type scope parsing")

    parts = scope_str.split(":")

    if len(parts) < 3:
        raise ValueError(
            f"Invalid scope format: '{scope_str}'. "
            f"Must be 'type:contentType:action[:anonymous]'"
        )

    scope_type = parts[0]
    content_type = parts[1]
    action = parts[2]
    is_anonymous = len(parts) >= 4 and parts[3] == "anonymous"

    # Validate type
    if scope_type not in VALID_TYPES:
        raise ValueError(f"Invalid type: '{scope_type}'. Must be one of {VALID_TYPES}")

    # Validate content type
    if not CONTENT_TYPE_PATTERN.match(content_type):
        raise ValueError(
            f"Invalid content type: '{content_type}'. "
            f"Must be valid content type or wildcard (e.g., text/markdown, text/*, *)"
        )

    # Validate action
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: '{action}'. Must be one of {VALID_ACTIONS}")

    return scope_type, content_type, action, is_anonymous


def content_type_matches(scope_content_type: str, required_content_type: str) -> bool:
    """
    Check if a scope content type matches a required content type (supports wildcards).

    Args:
        scope_content_type: Content type from scope (may contain wildcards)
        required_content_type: Required content type (no wildcards)

    Returns:
        True if matches

    Examples:
        content_type_matches("text/markdown", "text/markdown") -> True
        content_type_matches("text/*", "text/markdown") -> True
        content_type_matches("text/*", "text/plain") -> True
        content_type_matches("*", "application/json") -> True
        content_type_matches("text/markdown", "text/plain") -> False
    """
    if scope_content_type == "*":
        return True  # Universal wildcard

    if "/" not in scope_content_type:
        return False  # Invalid format

    scope_main, scope_sub = scope_content_type.split("/", 1)

    if "/" not in required_content_type:
        return False

    required_main, required_sub = required_content_type.split("/", 1)

    # Check main type
    if scope_main != "*" and scope_main != required_main:
        return False

    # Check subtype
    if scope_sub == "*":
        return True  # Wildcard subtype

    return scope_sub == required_sub


def check_scope(
    api_key: APIKeyEntity,
    scope_type: str,
    content_type: str,
    action: str,
    user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    raise_on_failure: bool = True,
) -> bool:
    """
    Check if an API key has permission for an action on a specific content type.

    Args:
        api_key: The API key entity to check
        scope_type: The type (resource, tool, prompt)
        content_type: The content type of the resource/tool
        action: The action being performed (read, write, search, invoke, etc.)
        user_id: The user ID if available (for identified access)
        resource_id: The specific resource ID (for resource_filters check)
        raise_on_failure: If True, raises HTTPException on failure. If False, returns bool

    Returns:
        True if authorized, False otherwise (only if raise_on_failure=False)

    Raises:
        HTTPException: If not authorized and raise_on_failure=True

    Examples:
        # Check if can read markdown
        check_scope(api_key, "resource", "text/markdown", "read", user_id="user-123")

        # Check if can invoke collection search tool
        check_scope(api_key, "tool", "application/vnd.agience.collection+json", "search")
    """
    # Validate inputs
    if scope_type not in VALID_TYPES:
        if raise_on_failure:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scope type: {scope_type}",
            )
        return False

    if action not in VALID_ACTIONS:
        if raise_on_failure:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action: {action}",
            )
        return False

    # Check each scope in the API key
    has_matching_scope = False
    for scope_str in api_key.scopes:
        try:
            s_type, s_content_type, s_action, s_is_anonymous = parse_scope(scope_str)

            # Check if this scope matches what we need
            if s_type == scope_type and s_action == action and content_type_matches(s_content_type, content_type):
                # Check anonymous vs identified
                if s_is_anonymous:
                    # Anonymous scope - always matches
                    has_matching_scope = True
                    break
                else:
                    # Identified scope - need user_id
                    if user_id:
                        has_matching_scope = True
                        break
        except ValueError:
            # Invalid scope format - skip it
            continue

    if not has_matching_scope:
        if raise_on_failure:
            detail = f"API key does not have {scope_type}:{content_type}:{action} permission"
            if not user_id:
                detail += " (or requires identified access but no user provided)"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail,
            )
        return False

    # Check resource filters if resource_id is specified
    if resource_id:
        # Extract resource type from scope_type (e.g., "resource" -> "collections" for collections)
        # For now, use simple mapping
        resource_type_map = {
            "resource": "collections",  # Will need refinement based on URI
            "tool": "tools",
            "prompt": "prompts",
        }
        resource_type = resource_type_map.get(scope_type)

        if resource_type and not api_key.can_access_resource(resource_type, resource_id):
            if raise_on_failure:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API key does not have access to {resource_type}/{resource_id}",
                )
            return False

    return True


def require_scope(
    api_key: Optional[APIKeyEntity],
    scope_type: str,
    content_type: str,
    action: str,
    user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
) -> None:
    """
    Require a specific scope, raising HTTPException if not authorized.

    This is a convenience function for use in router endpoints.

    Args:
        api_key: The API key entity (if using API key auth)
        scope_type: The type (resource, tool, prompt)
        content_type: The content type
        action: The action being performed
        user_id: The user ID if available
        resource_id: The specific resource ID

    Raises:
        HTTPException: If not authorized

    Examples:
        # Require read access to collections
        require_scope(api_key, "resource", "application/vnd.agience.collection+json", "read", user_id)

        # Require write access to markdown
        require_scope(api_key, "resource", "text/markdown", "write", user_id, resource_id="col-123")
    """
    if api_key is None:
        # No API key provided - this means JWT auth or no auth
        # For now, allow it (JWT auth has its own checks)
        return

    check_scope(
        api_key=api_key,
        scope_type=scope_type,
        content_type=content_type,
        action=action,
        user_id=user_id,
        resource_id=resource_id,
        raise_on_failure=True,
    )
