"""API schemas for generic secret management."""

from typing import Optional
from pydantic import BaseModel, Field


class SecretResponse(BaseModel):
    """A stored secret (encrypted value only populated when include_encrypted=True)."""
    id: str
    type: str
    provider: str
    label: str
    created_time: str
    is_default: bool
    authorizer_id: Optional[str] = None
    encrypted_value: Optional[str] = None
    expires_at: Optional[str] = None


class SecretFetchRequest(BaseModel):
    """Filter criteria for fetching a secret via delegation JWT."""
    type: Optional[str] = Field(None, description="Filter by secret type")
    provider: Optional[str] = Field(None, description="Filter by provider")
    authorizer_id: Optional[str] = Field(None, description="Filter by authorizer artifact ID")
    secret_id: Optional[str] = Field(None, description="Exact secret ID")


class SecretFetchResponse(BaseModel):
    """Secret wrapped as JWE for the requesting server."""
    id: str
    type: str
    jwe: dict


class SecretCreateRequest(BaseModel):
    """Request to store a new secret."""
    type: str = Field(
        description="Secret type: 'llm_key', 'github_token', 'integration_key', etc."
    )
    provider: str = Field(
        description="Provider: 'openai', 'anthropic', 'azure', 'github', etc."
    )
    label: str = Field(description="User-friendly name for this credential.")
    value: str = Field(description="Plaintext secret value (encrypted on server).")
    is_default: bool = False
    authorizer_id: Optional[str] = Field(None, description="Authorizer artifact that owns this secret")
    expires_at: Optional[str] = Field(None, description="ISO-8601 UTC expiry timestamp (for bearer tokens)")
