"""Origin /platform router — admin endpoints.

Settings + user admin moved here in 1.1e. Platform admin = the bootstrap
operator from `platform.operator_id`, OR a user holding `can_admin` (or
`can_update`) on the authority collection — whose ID is read from
`platform.authority_collection_id` settings.

`GET /platform/seed-collections` is intentionally not implemented here —
seed collections live in Mantle's Arango. A new `seed_collections_router`
on Mantle exposes the same data to admin UIs.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from origin.api.platform import PlatformUserResponse, PlatformUsersListResponse
from origin.db import grants as db_grants
from origin.db import persons as db_persons
from origin.db.session import get_db
from origin.services import grant_service
from origin.services.dependencies import AuthContext, get_auth
from origin.services.platform_settings_service import settings as platform_settings

logger = logging.getLogger(__name__)
platform_router = APIRouter(prefix="/platform", tags=["Platform"])


class SettingItem(BaseModel):
    key: str
    value: Optional[str] = None
    is_secret: bool = False


class UpdateSettingsRequest(BaseModel):
    settings: list[SettingItem]


class UpdateSettingsResponse(BaseModel):
    updated: int
    restart_required: bool = False


_RESTART_REQUIRED_KEYS = {
    "db.arango.host",
    "db.arango.port",
    "db.arango.username",
    "db.arango.password",
    "db.arango.database",
    "search.opensearch.host",
    "search.opensearch.port",
    "search.opensearch.username",
    "search.opensearch.password",
    "search.opensearch.use_ssl",
    "search.opensearch.verify_certs",
}


def _platform_admin_user_id(auth: AuthContext, db: Session) -> str:
    """Resolve the caller as platform admin or 403."""
    if not auth.user_id:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    operator_id = platform_settings.get("platform.operator_id")
    if operator_id and auth.user_id == operator_id:
        return auth.user_id
    authority_id = platform_settings.get("platform.authority_collection_id")
    if authority_id:
        if grant_service.user_has_any_flag(
            db, auth.user_id, authority_id, "can_admin", "can_update"
        ):
            return auth.user_id
    raise HTTPException(status_code=403, detail="Platform admin access required")


def _is_user_admin(db: Session, user_id: str) -> bool:
    operator_id = platform_settings.get("platform.operator_id")
    if operator_id and user_id == operator_id:
        return True
    authority_id = platform_settings.get("platform.authority_collection_id")
    if not authority_id:
        return False
    return grant_service.user_has_any_flag(
        db, user_id, authority_id, "can_admin", "can_update"
    )


def _settings_grouped(category: Optional[str] = None) -> dict[str, list[dict]]:
    """Read all settings from the cache, group by category. Secrets masked as None."""
    grouped: dict[str, list[dict]] = {}
    for key, value in platform_settings._values.items():  # noqa: SLF001 — internal
        cat = key.split(".")[0] if "." in key else "platform"
        if category and cat != category:
            continue
        grouped.setdefault(cat, []).append({"key": key, "value": value, "is_secret": False})
    for key in platform_settings._secrets:  # noqa: SLF001
        cat = key.split(".")[0] if "." in key else "platform"
        if category and cat != category:
            continue
        grouped.setdefault(cat, []).append({"key": key, "value": None, "is_secret": True})
    for entries in grouped.values():
        entries.sort(key=lambda e: e["key"])
    return grouped


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------
@platform_router.get("/settings")
async def get_all_settings(
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    _platform_admin_user_id(auth, db)
    return {"categories": _settings_grouped()}


@platform_router.get("/settings/{category}")
async def get_settings_by_category(
    category: str,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> list[dict]:
    _platform_admin_user_id(auth, db)
    grouped = _settings_grouped(category=category)
    return grouped.get(category, [])


@platform_router.patch("/settings", response_model=UpdateSettingsResponse)
async def update_settings(
    body: UpdateSettingsRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> UpdateSettingsResponse:
    admin_user_id = _platform_admin_user_id(auth, db)
    settings_dicts = []
    restart_required = False
    for item in body.settings:
        if item.is_secret and not item.value:
            continue
        if item.key in _RESTART_REQUIRED_KEYS:
            restart_required = True
        category = item.key.split(".")[0] if "." in item.key else "platform"
        settings_dicts.append(
            {
                "key": item.key,
                "value": item.value or "",
                "category": category,
                "is_secret": item.is_secret,
            }
        )
    platform_settings.set_many(db, settings_dicts, updated_by=admin_user_id)
    return UpdateSettingsResponse(updated=len(settings_dicts), restart_required=restart_required)


# ---------------------------------------------------------------------------
# User admin endpoints
# ---------------------------------------------------------------------------
@platform_router.get("/users", response_model=PlatformUsersListResponse)
async def list_users(
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    _platform_admin_user_id(auth, db)
    from sqlalchemy import select

    from origin.models.person import Person

    rows: Iterable = db.execute(select(Person).order_by(Person.created_time.asc())).scalars()
    users: List[PlatformUserResponse] = []
    for row in rows:
        users.append(
            PlatformUserResponse(
                id=str(row.id),
                email=row.email or "",
                name=row.name or "",
                picture=row.picture,
                is_platform_admin=_is_user_admin(db, str(row.id)),
                created_time=row.created_time.isoformat() if row.created_time else None,
            )
        )
    return PlatformUsersListResponse(users=users)


@platform_router.post("/users/{user_id}/grant-admin")
async def grant_platform_admin(
    user_id: str,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    admin_user_id = _platform_admin_user_id(auth, db)
    target = db_persons.get_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    authority_id = platform_settings.get("platform.authority_collection_id")
    if not authority_id:
        raise HTTPException(
            status_code=503,
            detail="platform.authority_collection_id is not configured",
        )
    grant_service.upsert_user_grant(
        db,
        user_id=user_id,
        resource_id=authority_id,
        granted_by=admin_user_id,
        flags={"can_read": True, "can_update": True, "can_admin": True},
        name="Platform admin (granted by admin)",
    )
    db.commit()
    return {"status": "granted", "user_id": user_id}


@platform_router.delete("/users/{user_id}/revoke-admin")
async def revoke_platform_admin(
    user_id: str,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
    admin_user_id = _platform_admin_user_id(auth, db)
    if user_id == admin_user_id:
        raise HTTPException(status_code=400, detail="Cannot revoke your own platform admin access")
    target = db_persons.get_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    authority_id = platform_settings.get("platform.authority_collection_id")
    if not authority_id:
        raise HTTPException(
            status_code=503,
            detail="platform.authority_collection_id is not configured",
        )
    grant_service.upsert_user_grant(
        db,
        user_id=user_id,
        resource_id=authority_id,
        granted_by=admin_user_id,
        flags={"can_read": True},
        name="Platform user (admin revoked)",
    )
    # Revoke any explicit admin/update grants left over.
    direct = db_grants.get_active_for_principal_resource(
        db, grantee_id=user_id, resource_id=authority_id
    )

    for g in direct:
        if g.can_admin or g.can_update:
            updates: dict = {"can_admin": False, "can_update": False}
            db_grants.update_grant(db, str(g.id), updates)
    db.commit()
    return {"status": "revoked", "user_id": user_id}
