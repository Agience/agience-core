# entities/commit.py
from typing import Optional, List, Dict, Any
from entities.base import BaseEntity

class Commit(BaseEntity):
    """
    Mirrors ArangoDB `Commit`:
      - message: string
      - timestamp: ISO8601 string
      - author_id: string
      - item_ids: list of CommitItem ids
    """
    PREFIX = "Commit"

    def __init__(
        self,
        id: Optional[str] = None,
        message: str = "",
        timestamp: Optional[str] = None,
        author_id: Optional[str] = None,
        subject_user_id: Optional[str] = None,
        presenter_type: Optional[str] = None,
        presenter_id: Optional[str] = None,
        client_id: Optional[str] = None,
        host_id: Optional[str] = None,
        server_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        api_key_id: Optional[str] = None,
        confirmation: str = "human_affirmed",
        changeset_type: str = "manual",
        item_ids: Optional[List[str]] = None,
        # BaseEntity fields (kept for local bookkeeping; not written to ArangoDB schema)
        created_time: Optional[str] = None,
        modified_time: Optional[str] = None,
    ):
        super().__init__(id=id, created_time=created_time, modified_time=modified_time)
        self.message = message
        self.timestamp = timestamp
        self.author_id = author_id
        self.subject_user_id = subject_user_id
        self.presenter_type = presenter_type
        self.presenter_id = presenter_id
        self.client_id = client_id
        self.host_id = host_id
        self.server_id = server_id
        self.agent_id = agent_id
        self.api_key_id = api_key_id
        self.confirmation = confirmation
        self.changeset_type = changeset_type
        self.item_ids = item_ids or []

    def to_dict(self) -> Dict[str, Any]:
        """
        Shape expected by db/arango writers and schema.
        Note: ArangoDB schema uses `timestamp`, not `created_time`.
        """
        base = self.to_dict_base()
        base.update({
            "message": self.message,
            "timestamp": self.timestamp,
            "author_id": self.author_id,
            "subject_user_id": self.subject_user_id,
            "presenter_type": self.presenter_type,
            "presenter_id": self.presenter_id,
            "client_id": self.client_id,
            "host_id": self.host_id,
            "server_id": self.server_id,
            "agent_id": self.agent_id,
            "api_key_id": self.api_key_id,
            "confirmation": self.confirmation,
            "changeset_type": self.changeset_type,
            "item_ids": list(self.item_ids),
        })
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Commit":
        base = cls.from_dict_base(data)
        return cls(
            id=base["id"],
            message=data.get("message", ""),
            timestamp=data.get("timestamp"),
            author_id=data.get("author_id"),
            subject_user_id=data.get("subject_user_id"),
            presenter_type=data.get("presenter_type"),
            presenter_id=data.get("presenter_id"),
            client_id=data.get("client_id"),
            host_id=data.get("host_id"),
            server_id=data.get("server_id"),
            agent_id=data.get("agent_id"),
            api_key_id=data.get("api_key_id"),
            confirmation=data.get("confirmation", "human_affirmed"),
            changeset_type=data.get("changeset_type", "manual"),
            item_ids=list(data.get("item_ids", [])),
            created_time=base["created_time"],
            modified_time=base["modified_time"],
        )
