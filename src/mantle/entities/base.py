import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

class BaseEntity:
    """
    Base domain entity with generated ID and timestamps.
    Note: created_time and modified_time are stored as ISO format strings.
    """
    PREFIX: Optional[str] = None

    def __init__(
        self,
        id: Optional[str] = None,
        created_time: Optional[str] = None,
        modified_time: Optional[str] = None
    ):
        self.id = id or self._generate_id()
        self.created_time: str = created_time or self._now_iso()
        self.modified_time: str = modified_time or self.created_time

    @classmethod
    def _generate_id(cls) -> str:
        """
        Generate a new UUID4 string.
        """
        return str(uuid.uuid4())

    @staticmethod
    def _now() -> datetime:
        """
        Return the current UTC datetime.
        """
        return datetime.now(timezone.utc)

    @staticmethod
    def _now_iso() -> str:
        """
        Return the current UTC datetime as ISO format string.
        """
        return datetime.now(timezone.utc).isoformat()

    def to_dict_base(self) -> Dict[str, Any]:
        """
        Serialize base fields for storage or transfer.
        """
        return {
            "id": self.id,
            "created_time": self.created_time,
            "modified_time": self.modified_time,
        }

    @classmethod
    def from_dict_base(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Populate base fields from a dict (e.g., DB row).
        """
        return {
            "id": data.get("id"),
            "created_time": data.get("created_time"),
            "modified_time": data.get("modified_time"),
        }

    def update_from_dict(self, updates: Dict[str, Any]) -> None:
        """
        Update mutable fields from a dict; refresh modified_time.
        """
        for key, value in updates.items():
            if key != "id" and hasattr(self, key):
                setattr(self, key, value)
        self.modified_time = self._now_iso()

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) and self.id == other.id

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.id}>"
