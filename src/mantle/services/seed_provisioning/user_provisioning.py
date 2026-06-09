"""Per-user first-login provisioning — the single declarative path.

On user create / first login the platform:
  1. ensures the user has an "Inbox" workspace (owner-grant side effects live in
     `workspace_service.create_workspace`),
  2. applies the declarative ``package/seeds/user`` grant artifacts with the
     user's context (``{{user.id}}``), and — when the user is the designated
     platform admin (``platform.operator_id``) — also the ``package/seeds/admin``
     grant set, and
  3. materializes the curated platform seed artifacts into that workspace,
     preserving any existing ordering.

Grants are uniform: same loader, same grant format. The only special thing is
that the one designated admin user receives the (fuller) admin grant set. Steps
1 and 3 loop over live DB state (not static data), so they stay as thin runtime
glue here; step 2 is pure declarative seeding via the loader.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from arango.database import StandardDatabase

from db.arango import (
    add_artifact_to_collection as db_add_artifact_to_collection,
    get_edge as db_get_edge,
    list_collection_artifacts as db_list_collection_artifacts,
)
from services.bootstrap_types import INBOX_MATERIALIZATION_SLUGS
from services.platform_topology import get_id_optional
from .loader import UserContext, seed_from_artifacts

logger = logging.getLogger(__name__)


def _seeds_base() -> Path:
    env = os.getenv("AGIENCE_SEEDS_ROOT")
    if env:
        return Path(env)
    # BASE_DIR is /app in Docker and the repo root in local dev, so the
    # seed tree resolves correctly in both without an env override.
    from kernel import config
    return config.BASE_DIR / "package" / "seeds"


def _is_platform_admin(arango_db: StandardDatabase, user_id: str) -> bool:
    """The designated platform admin is the user in ``platform.operator_id``."""
    from services.platform_settings_service import settings

    return bool(user_id) and settings.get("platform.operator_id") == user_id


def provision_user(
    arango_db: StandardDatabase,
    user_id: str,
    *,
    email: Optional[str] = None,
    name: Optional[str] = None,
    seeds_base: Optional[Path] = None,
) -> None:
    """Provision a user on first login: ensure Inbox workspace, apply the user
    grant seeds (plus the admin grant set if this is the designated admin), and
    materialize curated seed artifacts. Idempotent."""
    if not user_id:
        logger.warning("provision_user called with empty user_id — skipping")
        return

    base = seeds_base or _seeds_base()
    inbox_id = _ensure_inbox_workspace(arango_db, user_id)
    ctx = UserContext(id=user_id, email=email, name=name, inbox_id=inbox_id)

    _apply_grant_set(arango_db, base / "user", ctx, user_id)
    if _is_platform_admin(arango_db, user_id):
        _apply_grant_set(arango_db, base / "admin", ctx, user_id)

    if inbox_id:
        _materialize_inbox(arango_db, user_id, inbox_id)


def _apply_grant_set(
    arango_db: StandardDatabase, root: Path, ctx: UserContext, user_id: str
) -> None:
    report = seed_from_artifacts(arango_db, root, user=ctx)
    for err in report.errors:
        logger.warning("provision_user (%s): %s", user_id, err)


def _ensure_inbox_workspace(arango_db: StandardDatabase, user_id: str) -> Optional[str]:
    """Return the user's primary (oldest) workspace id, creating an "Inbox"
    workspace on first login. ``create_workspace`` issues the owner grant."""
    from services import workspace_service

    existing = workspace_service.list_workspaces(arango_db, user_id)
    if existing:
        primary = min(existing, key=lambda w: getattr(w, "created_time", "") or "")
        return primary.id
    new_ws = workspace_service.create_workspace(arango_db, user_id, "Inbox")
    return new_ws.id


def _materialize_inbox(arango_db: StandardDatabase, user_id: str, inbox_workspace_id: str) -> None:
    """Link curated platform seed artifacts into the user's Inbox workspace.

    Skips artifacts already linked so user/operator reordering (``order_key``) is
    never clobbered on re-run.
    """
    seen: set[str] = set()
    for slug in INBOX_MATERIALIZATION_SLUGS:
        col_id = get_id_optional(slug)
        if not col_id:
            continue
        try:
            artifacts = db_list_collection_artifacts(arango_db, col_id)
        except Exception:
            logger.exception("Failed loading seed artifacts from collection %s", slug)
            continue

        for artifact in artifacts or []:
            root_id = str(
                (artifact.get("root_id", "") if isinstance(artifact, dict)
                 else getattr(artifact, "root_id", "")) or ""
            ).strip()
            if not root_id or root_id in seen:
                continue
            seen.add(root_id)

            # Skip if already linked — avoids resetting order_key on every login.
            if db_get_edge(arango_db, inbox_workspace_id, root_id):
                continue
            try:
                db_add_artifact_to_collection(arango_db, inbox_workspace_id, root_id)
            except Exception:
                logger.exception(
                    "Failed importing seed artifact root %s into inbox workspace %s",
                    root_id, inbox_workspace_id,
                )
