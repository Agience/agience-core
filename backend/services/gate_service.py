"""Entitlement gate — kernel enforcement for resource limits.

Core compares numbers. It never knows about Stripe, plan names, or
subscription state. Ophan pushes numeric limits via POST /internal/gate/set-limits;
this service reads them and compares against live counts or accumulated tallies.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from arango.database import StandardDatabase

from core import config

logger = logging.getLogger(__name__)

# Collection names
_ENTITLEMENT_CACHE = "entitlement_cache"
_USAGE_TALLIES = "usage_tallies"

# Free-tier defaults — used when no entitlement_cache row exists for a person.
_FREE_DEFAULTS = {
    "max_workspaces": 1,
    "max_artifacts": 500,
    "vu_limit": 100,
}


def enforcement_enabled() -> bool:
    """True when billing enforcement is active (SaaS production only)."""
    return bool(config.BILLING_ENFORCEMENT_ENABLED)


# ---------------------------------------------------------------------------
# Entitlement cache (limits pushed by Ophan)
# ---------------------------------------------------------------------------

def get_limits(db: StandardDatabase, person_id: str) -> Optional[dict]:
    """Read cached limits for a person, or None if no row."""
    coll = db.collection(_ENTITLEMENT_CACHE)
    if not coll.has(person_id):
        return None
    doc = coll.get(person_id)
    return {
        "max_workspaces": doc.get("max_workspaces"),
        "max_artifacts": doc.get("max_artifacts"),
        "vu_limit": doc.get("vu_limit"),
    }


def get_or_default_limits(db: StandardDatabase, person_id: str) -> dict:
    """Read cached limits, falling back to free-tier defaults."""
    return get_limits(db, person_id) or dict(_FREE_DEFAULTS)


def set_limits(
    db: StandardDatabase,
    person_id: str,
    *,
    max_workspaces: Optional[int] = None,
    max_artifacts: Optional[int] = None,
    vu_limit: Optional[int] = None,
) -> None:
    """Upsert entitlement cache row. Called by Ophan via the gate router."""
    coll = db.collection(_ENTITLEMENT_CACHE)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_key": person_id,
        "person_id": person_id,
        "max_workspaces": max_workspaces,
        "max_artifacts": max_artifacts,
        "vu_limit": vu_limit,
        "updated_at": now,
    }
    if coll.has(person_id):
        coll.update(doc)
    else:
        coll.insert(doc)


# ---------------------------------------------------------------------------
# Usage tallies (consumable resources — VU only)
# ---------------------------------------------------------------------------

def get_tally(db: StandardDatabase, person_id: str, dimension: str, period: str) -> int:
    """Read accumulated tally for a dimension/period, or 0."""
    key = f"{person_id}:{dimension}:{period}"
    coll = db.collection(_USAGE_TALLIES)
    if not coll.has(key):
        return 0
    doc = coll.get(key)
    return doc.get("total", 0)


def add_tally(
    db: StandardDatabase,
    person_id: str,
    dimension: str,
    period: str,
    amount: int = 1,
) -> int:
    """Increment a tally, creating the row if needed. Returns new total."""
    key = f"{person_id}:{dimension}:{period}"
    coll = db.collection(_USAGE_TALLIES)
    now = datetime.now(timezone.utc).isoformat()

    if coll.has(key):
        result = db.aql.execute(
            "UPDATE {_key: @key} WITH {total: OLD.total + @amount, updated_at: @now} IN @@coll RETURN NEW",
            bind_vars={"key": key, "amount": amount, "now": now, "@coll": _USAGE_TALLIES},
        )
        doc = next(result)
        return doc.get("total", 0)
    else:
        doc = {
            "_key": key,
            "person_id": person_id,
            "dimension": dimension,
            "period": period,
            "total": amount,
            "updated_at": now,
        }
        coll.insert(doc)
        return amount


def get_all_tallies(db: StandardDatabase, person_id: str) -> dict:
    """Return all tallies for a person, grouped by dimension then period."""
    cursor = db.aql.execute(
        "FOR doc IN @@coll FILTER doc.person_id == @pid RETURN doc",
        bind_vars={"@coll": _USAGE_TALLIES, "pid": person_id},
    )
    result: dict = {}
    for doc in cursor:
        result.setdefault(doc["dimension"], {})[doc["period"]] = doc.get("total", 0)
    return result


# ---------------------------------------------------------------------------
# Live counts (workspaces, artifacts — not tallied, queried in real time)
# ---------------------------------------------------------------------------

def count_workspaces(db: StandardDatabase, person_id: str) -> int:
    """Count workspaces owned by this person, excluding the inbox.

    Unified store: a workspace is a `Collection` with content_type=workspace.
    The inbox collection is keyed by the person_id, so we exclude it explicitly.
    """
    from entities.collection import WORKSPACE_CONTENT_TYPE

    cursor = db.aql.execute(
        "FOR c IN artifacts "
        "FILTER c.created_by == @pid AND c.content_type == @ws_content_type AND c._key != @pid "
        "COLLECT WITH COUNT INTO n RETURN n",
        bind_vars={"pid": person_id, "ws_content_type": WORKSPACE_CONTENT_TYPE},
    )
    return next(cursor, 0)


def count_artifacts(db: StandardDatabase, person_id: str) -> int:
    """Count non-archived artifacts created by this person across all containers."""
    cursor = db.aql.execute(
        "FOR a IN artifacts "
        "FILTER a.created_by == @pid AND a.state != 'archived' "
        "COLLECT WITH COUNT INTO n RETURN n",
        bind_vars={"pid": person_id},
    )
    return next(cursor, 0)
