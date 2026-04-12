from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class AgentOptions(BaseModel):
    preview: bool = Field(
        default=True,
        description="When true, the agent should not mutate state and only return proposed actions.",
    )
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    timeout_ms: Optional[int] = Field(default=15000, ge=1000)


class AgentRequest(BaseModel):
    operator: str = Field(description="Operator name or identifier.")
    workspace_id: Optional[str] = Field(
        default=None, description="Workspace ID the operator runs in (required for artifact actions)."
    )
    selected_artifact_ids: List[str] = Field(
        default_factory=list,
        description="Optional list of artifact IDs to operate on.",
    )
    input: Optional[str] = Field(
        default=None, description="Free-form input or prompt; meaning depends on the operator."
    )
    params: Dict[str, Any] = Field(
        default_factory=dict, description="Structured parameters for the operator."
    )
    options: AgentOptions = Field(default_factory=AgentOptions)


class WorkspaceArtifactDraft(BaseModel):
    """Minimal draft for creating a new workspace artifact.

    Keep this schema lean and DB-agnostic. Services will enrich/validate.
    """

    title: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    content: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    content_type: Optional[str] = None


class ArtifactPatch(BaseModel):
    artifact_id: str
    patch: Dict[str, Any] = Field(
        default_factory=dict,
        description="Partial fields to update on the artifact (e.g., title, description, tags, context).*",
    )


class CreateArtifactAction(BaseModel):
    type: Literal["create_artifact"] = "create_artifact"
    draft: WorkspaceArtifactDraft


class UpdateArtifactAction(BaseModel):
    type: Literal["update_artifact"] = "update_artifact"
    artifact_id: str
    patch: Dict[str, Any]


class DeleteArtifactAction(BaseModel):
    type: Literal["delete_artifact"] = "delete_artifact"
    artifact_id: str


class LogAction(BaseModel):
    type: Literal["log"] = "log"
    level: Literal["info", "warn", "error"] = "info"
    message: str

# Workspace-level attachment actions (preview/apply by service in future):

class AttachCollectionAction(BaseModel):
    type: Literal["attach_collection"] = "attach_collection"
    workspace_id: Optional[str] = None
    collection_id: str
    mode: Literal["own", "shared"] = "own"


AgentAction = Union[
    CreateArtifactAction,
    UpdateArtifactAction,
    DeleteArtifactAction,
    LogAction,
    AttachCollectionAction,
]


class AgentDiagnostics(BaseModel):
    usage_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    warnings: List[str] = Field(default_factory=list)


class AgentResponse(BaseModel):
    actions: List[AgentAction] = Field(default_factory=list)
    messages: List[str] = Field(default_factory=list)
    diagnostics: AgentDiagnostics = Field(default_factory=AgentDiagnostics)


class AgentError(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
