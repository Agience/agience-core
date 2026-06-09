# entities/person.py

from typing import Optional, Dict, Any
from entities.base import BaseEntity

class Person(BaseEntity):
    """
    Domain entity for a user/Person.
    """
    PREFIX = "Person"

    def __init__(
        self,
        id: Optional[str] = None,
        google_id: str = "",
        oidc_provider: str = "",
        oidc_subject: str = "",
        email: str = "",
        name: str = "",
        username: str = "",
        picture: Optional[str] = None,
        password_hash: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None,
        created_time: Optional[str] = None,
        modified_time: Optional[str] = None,
    ):
        # Only set the id at the base; timestamps come from the caller
        super().__init__(id=id, created_time=created_time, modified_time=modified_time)
        self.google_id = google_id
        self.oidc_provider = oidc_provider
        self.oidc_subject = oidc_subject
        self.email = email
        self.name = name
        self.username = username
        self.picture = picture
        self.password_hash = password_hash
        self.preferences = preferences or {}

    def to_dict(self) -> Dict[str, Any]:
        base = self.to_dict_base()
        base.update({
            "google_id": self.google_id,
            "oidc_provider": self.oidc_provider,
            "oidc_subject": self.oidc_subject,
            "email": self.email,
            "name": self.name,
            "username": self.username,
            "picture": self.picture,
            "preferences": self.preferences,
            "has_password": bool(self.password_hash),
        })
        return base

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Person":
        base = cls.from_dict_base(data)
        return cls(
            id=base["id"],
            google_id=data.get("google_id", ""),
            oidc_provider=data.get("oidc_provider", ""),
            oidc_subject=data.get("oidc_subject", ""),
            email=data.get("email", ""),
            name=data.get("name", ""),
            username=data.get("username", ""),
            picture=data.get("picture"),
            password_hash=data.get("password_hash"),
            preferences=data.get("preferences"),
            created_time=data.get("created_time"),
            modified_time=data.get("modified_time"),
        )
