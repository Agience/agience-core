# /api/collections/commit.py

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CommitItem(BaseModel):
    """
    One atomic change set for a single collection.
    - item_type: "add" to link versions, "remove" to unlink versions, "relate" reserved.
    - artifact_version_ids: list of version ids affected by this item.
    """
    collection_id: str
    item_type: Literal["add", "remove", "relate"]
    artifact_version_ids: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CommitCreate(BaseModel):
    """
    A single commit that may span multiple collections.
    The server will create one Commit document and multiple CommitItem documents.
    """
    message: Optional[str] = None
    items: List[CommitItem]

    model_config = ConfigDict(extra="forbid")


class CommitResponse(BaseModel):
    """
    Mirrors the stored Commit shape.
    """
    id: str
    message: str
    author_id: str
    subject_user_id: Optional[str] = None
    presenter_type: Optional[str] = None
    presenter_id: Optional[str] = None
    client_id: Optional[str] = None
    host_id: Optional[str] = None
    server_id: Optional[str] = None
    agent_id: Optional[str] = None
    api_key_id: Optional[str] = None
    confirmation: Optional[str] = None
    changeset_type: Optional[str] = None
    timestamp: datetime
    item_ids: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
