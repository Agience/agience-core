# /entities/api_key.py

from typing import Optional, Dict, Any, List
from entities.base import BaseEntity

class APIKey(BaseEntity):
    """
    Domain entity for an ArangoDB API Key.
    Scoped API keys for programmatic access to Agience MCP and collections.
    
    Scope Format: [type]:[contentType]:[action][:anonymous]
    Special System Scopes:
    - licensing:entitlement:<entitlement_name>
    - Type: resource, tool, prompt (maps to MCP primitives)
    - Content Type: Standard content type or wildcard (e.g., text/markdown, text/*, *)
    - Action: read, write, search, invoke, delete, create
    - Anonymous: Optional :anonymous suffix (default is identified)
    
    Examples:
    - ["resource:application/vnd.agience.collection+json:read"] - read collections (identified)
    - ["resource:text/markdown:write:anonymous"] - write markdown (anonymous)
    - ["tool:application/vnd.agience.collection+json:search"] - search collections tool
    - ["resource:text/*:read"] - read all text types (wildcard)
    - ["tool:*:invoke"] - invoke any tool (superuser)
    
    Resource Filters:
    - Limit access to specific resources by ID
    - {"collections": ["col-123", "col-456"]} - only these collections
    - {"collections": "*"} - all collections
    - {"workspaces": "*", "collections": ["col-123"]} - all workspaces, one collection
    """

    PREFIX = "APIKey"

    def __init__(
        self,
        id: Optional[str] = None,
        user_id: str = "",
        name: str = "",
        client_id: Optional[str] = None,
        host_id: Optional[str] = None,
        server_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        display_label: Optional[str] = None,
        issued_by_user_id: Optional[str] = None,
        created_from_client_id: Optional[str] = None,
        key_hash: str = "",
        requires_nonce: bool = False,
        scopes: Optional[List[str]] = None,
        resource_filters: Optional[Dict[str, Any]] = None,
        created_time: Optional[str] = None,
        modified_time: Optional[str] = None,
        expires_at: Optional[str] = None,
        last_used_at: Optional[str] = None,
        is_active: bool = True,
    ):
        super().__init__(id=id, created_time=created_time, modified_time=modified_time)

        self.user_id = user_id
        self.name = name
        self.client_id = client_id
        self.host_id = host_id
        self.server_id = server_id
        self.agent_id = agent_id
        self.display_label = display_label
        self.issued_by_user_id = issued_by_user_id
        self.created_from_client_id = created_from_client_id
        self.key_hash = key_hash
        self.requires_nonce = requires_nonce
        self.scopes = scopes or []
        self.resource_filters = resource_filters or {}
        self.expires_at = expires_at
        self.last_used_at = last_used_at
        self.is_active = is_active

    def to_dict(self) -> Dict[str, Any]:
        """Serialize APIKey (never includes raw key, only hash)."""
        base = self.to_dict_base()
        base.update({
            "user_id": self.user_id,
            "name": self.name,
            "client_id": self.client_id,
            "host_id": self.host_id,
            "server_id": self.server_id,
            "agent_id": self.agent_id,
            "display_label": self.display_label,
            "issued_by_user_id": self.issued_by_user_id,
            "created_from_client_id": self.created_from_client_id,
            "key_hash": self.key_hash,
            "requires_nonce": self.requires_nonce,
            "scopes": self.scopes,
            "resource_filters": self.resource_filters,
            "expires_at": self.expires_at,
            "last_used_at": self.last_used_at,
            "is_active": self.is_active,
        })
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "APIKey":
        """Deserialize from ArangoDB document."""
        base = cls.from_dict_base(data)
        return cls(
            id=base["id"],
            user_id=data.get("user_id", ""),
            name=data.get("name", ""),
            client_id=data.get("client_id"),
            host_id=data.get("host_id"),
            server_id=data.get("server_id"),
            agent_id=data.get("agent_id"),
            display_label=data.get("display_label"),
            issued_by_user_id=data.get("issued_by_user_id"),
            created_from_client_id=data.get("created_from_client_id"),
            key_hash=data.get("key_hash", ""),
            requires_nonce=data.get("requires_nonce", False),
            scopes=data.get("scopes", []),
            resource_filters=data.get("resource_filters", {}),
            created_time=base["created_time"],
            modified_time=base["modified_time"],
            expires_at=data.get("expires_at"),
            last_used_at=data.get("last_used_at"),
            is_active=data.get("is_active", True),
        )

    def has_scope(self, scope_type: str, content_type: str, action: str, is_anonymous: bool = False) -> bool:
        """
        Check if this key has a specific scope (with wildcard support).

        Args:
            scope_type: resource, tool, or prompt
            content_type: Content type (e.g., text/markdown)
            action: read, write, search, invoke, delete, create
            is_anonymous: Whether anonymous access is required

        Returns:
            True if the key has a matching scope
        """
        from core.scopes import parse_scope, content_type_matches

        for scope_str in self.scopes:
            try:
                s_type, s_content_type, s_action, s_is_anonymous = parse_scope(scope_str)

                # Check type and action match
                if s_type != scope_type or s_action != action:
                    continue

                # Check content type matches (with wildcard support)
                if not content_type_matches(s_content_type, content_type):
                    continue

                # Check anonymous flag
                if is_anonymous and not s_is_anonymous:
                    continue  # Need anonymous but scope is identified

                # If not requiring anonymous, either works
                return True

            except ValueError:
                # Invalid scope format - skip
                continue

        return False

    def can_access_resource(self, resource_type: str, resource_id: Optional[str] = None) -> bool:
        """
        Check if this key can access a specific resource.
        
        resource_filters format:
        {
            "collections": ["col_123", "col_456"],  # specific IDs
            "workspaces": "*",  # all workspaces
            "tools": ["search_collections", "create_collection"]
        }
        """
        if not self.resource_filters:
            return True  # No filters = access to all

        filter_value = self.resource_filters.get(resource_type)
        if filter_value is None:
            return False  # Type not in filters = no access

        if filter_value == "*":
            return True  # Wildartifact = access to all of this type

        if isinstance(filter_value, list):
            if resource_id is None:
                return len(filter_value) > 0  # Has access to some resources of this type
            return resource_id in filter_value  # Check specific ID

        return False
