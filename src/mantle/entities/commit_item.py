# entities/commit_item.py
from typing import Optional, List, Dict, Any
from entities.base import BaseEntity

class CommitItem(BaseEntity):
    """
    Mirrors ArangoDB `CommitItem`:
      - item_type: "add" | "remove" | "relate"
      - collection_id: optional (MVP always sets it)
      - artifact_version_ids: list of version ids affected
    """
    PREFIX = "CommitItem"

    VALID_ITEM_TYPES = {"add", "remove", "relate"}

    def __init__(
        self,
        id: Optional[str] = None,
        item_type: str = "add",
        artifact_version_ids: Optional[List[str]] = None,
        collection_id: Optional[str] = None,
        created_time: Optional[str] = None,
        modified_time: Optional[str] = None,
    ):
        super().__init__(id=id, created_time=created_time, modified_time=modified_time)
        if item_type not in self.VALID_ITEM_TYPES:
            raise ValueError(f"Invalid item_type '{item_type}', must be one of {self.VALID_ITEM_TYPES}")
        self.item_type = item_type
        self.artifact_version_ids = artifact_version_ids or []
        self.collection_id = collection_id

    def to_dict(self) -> Dict[str, Any]:
        base = self.to_dict_base()
        base.update({
            "item_type": self.item_type,
            "collection_id": self.collection_id,
            "artifact_version_ids": list(self.artifact_version_ids),
        })
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommitItem":
        base = cls.from_dict_base(data)
        return cls(
            id=base["id"],
            item_type=data.get("item_type", "relate"),
            artifact_version_ids=data.get("artifact_version_ids", []),
            collection_id=data.get("collection_id"),
            created_time=base["created_time"],
            modified_time=base["modified_time"],
        )
