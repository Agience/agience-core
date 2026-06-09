from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class CommitWarning(BaseModel):
    """Non-blocking warnings to surface in commit preview/commit UI."""

    code: str
    message: str
    artifact_id: Optional[str] = None
    kind: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class CollectionCommitSummary(BaseModel):
    """Per-collection log of commit operations."""

    collection_id: str
    commit_id: Optional[str] = None
    adds: List[str] = []
    removes: List[str] = []
    confirmation: Optional[str] = None
    changeset_type: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class CollectionChangeSummary(BaseModel):
    """UI-friendly summary of membership changes per collection."""

    collection_id: str
    added_artifacts: List[str] = []
    removed_artifacts: List[str] = []
    blocked_adds: List[str] = []
    blocked_removes: List[str] = []

    model_config = ConfigDict(extra="forbid")


class ArtifactCommitChange(BaseModel):
    """Describes how a single workspace artifact will change as part of a commit."""

    artifact_id: str
    root_id: Optional[str] = None
    action: str  # new | modified | membership | archived | noop | skipped
    state_before: Optional[str] = None
    state_after: Optional[str] = None
    target_collections: List[str] = []
    committed_collections: List[str] = []
    adds: List[str] = []
    removes: List[str] = []
    blocked_adds: List[str] = []
    blocked_removes: List[str] = []
    skipped_reason: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class WorkspaceCommitPlanSummary(BaseModel):
    """Aggregated commit plan encompassing artifact-level and collection-level diffs."""

    artifacts: List[ArtifactCommitChange] = []
    collections: List[CollectionChangeSummary] = []
    warnings: List[CommitWarning] = []
    total_artifacts: int = 0
    total_adds: int = 0
    total_removes: int = 0
    blocked_collections: List[str] = []

    model_config = ConfigDict(extra="forbid")


class WorkspaceCommitRequest(BaseModel):
    """Optional payload for commit/preview endpoints."""

    artifact_ids: Optional[List[str]] = None
    dry_run: bool = False
    commit_token: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class CommitActorSummary(BaseModel):
    actor_type: str
    actor_id: str
    subject_user_id: Optional[str] = None
    presenter_type: Optional[str] = None
    presenter_id: Optional[str] = None
    client_id: Optional[str] = None
    host_id: Optional[str] = None
    server_id: Optional[str] = None
    agent_id: Optional[str] = None
    api_key_id: Optional[str] = None
    commit_authorized_by_flag: bool = False

    model_config = ConfigDict(extra="forbid")


class WorkspaceCommitResponse(BaseModel):
    workspace_id: str
    plan: WorkspaceCommitPlanSummary
    actor: CommitActorSummary
    dry_run: bool = False
    commit_token: Optional[str] = None
    updated_workspace_artifacts: List[dict] = []
    deleted_workspace_artifact_ids: List[str] = []
    skipped_workspace_artifact_ids: List[str] = []
    per_collection: List[CollectionCommitSummary] = []

    model_config = ConfigDict(extra="forbid")


# Preview response reuses the same schema for now.
WorkspaceCommitPreviewResponse = WorkspaceCommitResponse

