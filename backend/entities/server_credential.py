# /entities/server_credential.py

from typing import Optional, Dict, Any, List
from entities.base import BaseEntity


class ServerCredential(BaseEntity):
    """
    Domain entity for a registered server credential in ArangoDB.

    Kernel servers authenticate via OAuth 2.0 client_credentials grant.
    Each server has a well-known client_id and a bcrypt-hashed client_secret.
    The credential carries the full identity chain (authority, host, server)
    that is stamped into every JWT issued to the server.
    """

    PREFIX = "ServerCredential"

    def __init__(
        self,
        id: Optional[str] = None,
        client_id: str = "",
        name: str = "",
        secret_hash: str = "",
        authority: str = "",
        host_id: str = "",
        server_id: str = "",
        scopes: Optional[List[str]] = None,
        resource_filters: Optional[Dict[str, Any]] = None,
        user_id: str = "",
        is_active: bool = True,
        created_time: Optional[str] = None,
        modified_time: Optional[str] = None,
        last_used_at: Optional[str] = None,
        last_rotated_at: Optional[str] = None,
    ):
        super().__init__(id=id, created_time=created_time, modified_time=modified_time)

        self.client_id = client_id
        self.name = name
        self.secret_hash = secret_hash
        self.authority = authority
        self.host_id = host_id
        self.server_id = server_id
        self.scopes = scopes or ["tool:*:invoke", "resource:*:read"]
        self.resource_filters = resource_filters or {"workspaces": "*", "collections": "*"}
        self.user_id = user_id
        self.is_active = is_active
        self.last_used_at = last_used_at
        self.last_rotated_at = last_rotated_at

    def to_dict(self) -> Dict[str, Any]:
        base = self.to_dict_base()
        base.update({
            "client_id": self.client_id,
            "name": self.name,
            "secret_hash": self.secret_hash,
            "authority": self.authority,
            "host_id": self.host_id,
            "server_id": self.server_id,
            "scopes": self.scopes,
            "resource_filters": self.resource_filters,
            "user_id": self.user_id,
            "is_active": self.is_active,
            "last_used_at": self.last_used_at,
            "last_rotated_at": self.last_rotated_at,
        })
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerCredential":
        return cls(
            id=data.get("_key") or data.get("id"),
            client_id=data.get("client_id", ""),
            name=data.get("name", ""),
            secret_hash=data.get("secret_hash", ""),
            authority=data.get("authority", ""),
            host_id=data.get("host_id", ""),
            server_id=data.get("server_id", ""),
            scopes=data.get("scopes"),
            resource_filters=data.get("resource_filters"),
            user_id=data.get("user_id", ""),
            is_active=data.get("is_active", True),
            created_time=data.get("created_time"),
            modified_time=data.get("modified_time"),
            last_used_at=data.get("last_used_at"),
            last_rotated_at=data.get("last_rotated_at"),
        )
