# entities/collection_artifact.py

from typing import Optional, Dict, Any
from entities.base import BaseEntity

class CollectionArtifact(BaseEntity):
    """
    Link entity for (collection_id, artifact_root_id) -> artifact_version_id (specific version).
    """

    PREFIX = "CollectionArtifact"

    def __init__(
        self,
        id: Optional[str] = None,
        collection_id: str = "",
        artifact_root_id: str = "",
        artifact_version_id: str = "",
    ):
        super().__init__(id=id)
        self.collection_id = collection_id
        self.artifact_root_id = artifact_root_id
        self.artifact_version_id = artifact_version_id

        if not (collection_id and artifact_root_id and artifact_version_id):
            raise ValueError("collection_id, artifact_root_id, and artifact_version_id are all required")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collection_id": self.collection_id,
            "artifact_root_id": self.artifact_root_id,
            "artifact_version_id": self.artifact_version_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CollectionArtifact":
        base = cls.from_dict_base(data)
        artifact_version_id = data.get("artifact_version_id")
        if not artifact_version_id:
            raise ValueError("artifact_version_id is required")
        artifact_root_id = data.get("artifact_root_id")
        if not artifact_root_id:
            raise ValueError("artifact_root_id is required")
        return cls(
            id=base["id"],
            collection_id=data["collection_id"],
            artifact_root_id=artifact_root_id,
            artifact_version_id=artifact_version_id,
        )
