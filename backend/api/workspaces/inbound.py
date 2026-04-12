from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class InboundMessageRequest(BaseModel):
    text: str = Field(description="Inbound message text content")
    channel: Optional[str] = Field(default=None, description="Source channel identifier, e.g., 'telegram' or 'sms'")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context to embed in artifact.context")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Opaque metadata from the sender")

    model_config = ConfigDict(extra="forbid")


class InboundMessageResponse(BaseModel):
    workspace_id: str
    source_artifact_id: str
    artifact_id: str
    processed: bool = False
    forwarded: bool = False
    output_text: Optional[str] = None

    model_config = ConfigDict(extra="forbid")
