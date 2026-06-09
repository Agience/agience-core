"""
Platform topology: runtime ID registry.

All platform-owned collections and artifacts use random UUIDs as their
primary IDs (_key in ArangoDB). Slugs (defined in bootstrap_types) are
human-readable keys that map to those UUIDs.

The slug→UUID mappings are persisted in the ``platform_settings`` collection
(keys: ``platform.id.<slug>``). On restart, ``pre_resolve_platform_ids()``
loads them from settings — no slug-based AQL scans required.

On first boot the UUIDs are generated, registered in-memory, and written to
``platform_settings`` so subsequent boots are deterministic.
"""

import logging
from typing import Optional

from arango.database import StandardDatabase

from services.bootstrap_types import (
    AGIENCE_CORE_SLUG,
    ALL_PLATFORM_COLLECTION_SLUGS,
    AUTHORITY_ARTIFACT_SLUG,
    HOST_ARTIFACT_SLUG,
    AGENCY_ARTIFACT_SLUG,
    AGENT_ARTIFACT_SLUG_PREFIX,
    LLM_CONNECTION_SLUG_PREFIX,
    SERVER_ARTIFACT_SLUG_PREFIX,
    PLATFORM_AGENT_SLUGS,
    PLATFORM_LLM_CONNECTION_SLUGS,
)

logger = logging.getLogger(__name__)

# Prefix used when persisting slug→UUID mappings in platform_settings.
_SETTINGS_PREFIX = "platform.id."

# ---------------------------------------------------------------------------
# Runtime ID registry
# Populated at startup by pre_resolve_platform_ids(), queried at request time.
# ---------------------------------------------------------------------------

_registry: dict[str, str] = {}


def register_id(slug: str, uuid_id: str) -> None:
    """Register a slug -> UUID mapping (called during bootstrap)."""
    _registry[slug] = uuid_id


def get_id(slug: str) -> str:
    """
    Get the UUID for a platform slug.
    Raises RuntimeError if the slug hasn't been registered yet.
    """
    if slug not in _registry:
        raise RuntimeError(
            f"Platform slug '{slug}' not registered. "
            "Was pre_resolve_platform_ids() called at startup?"
        )
    return _registry[slug]


def get_id_optional(slug: str) -> Optional[str]:
    """Get the UUID for a platform slug, or None if not registered."""
    return _registry.get(slug)


def get_all_platform_collection_ids() -> list[str]:
    """Return UUIDs for all registered platform-owned collections (admin grant
    iteration). Skips any slug not yet registered so one missing seed can't nuke
    the whole operator grant loop — drift is caught by the seed tests, not here."""
    return [cid for cid in (get_id_optional(s) for s in ALL_PLATFORM_COLLECTION_SLUGS) if cid]


def clear_registry() -> None:
    """Clear the registry (used in tests)."""
    _registry.clear()


# ---------------------------------------------------------------------------
# Bootstrap pre-resolution
# ---------------------------------------------------------------------------

def _all_platform_slugs() -> list[str]:
    """Return every slug that needs an ID mapping."""
    from services import server_registry

    slugs: list[str] = []
    slugs.extend(ALL_PLATFORM_COLLECTION_SLUGS)
    slugs.extend([AUTHORITY_ARTIFACT_SLUG, HOST_ARTIFACT_SLUG, AGENCY_ARTIFACT_SLUG])
    slugs.append(AGIENCE_CORE_SLUG)
    slugs.extend(f"{AGENT_ARTIFACT_SLUG_PREFIX}{s}" for s in PLATFORM_AGENT_SLUGS)
    slugs.extend(f"{LLM_CONNECTION_SLUG_PREFIX}{s}" for s in PLATFORM_LLM_CONNECTION_SLUGS)
    slugs.extend(f"{SERVER_ARTIFACT_SLUG_PREFIX}{name}" for name in server_registry.all_names())
    return slugs


def pre_resolve_platform_ids(arango_db: StandardDatabase) -> None:
    """
    Load already-persisted platform slug→UUID mappings from settings into the
    in-memory registry at startup. Fallback-only: this does NOT mint IDs.

    The declarative seed loader (``seed_provisioning.loader``) is the sole ID
    authority — on a fresh DB it derives deterministic uuid5 IDs and persists
    them to ``platform_settings``. This function reloads those on subsequent
    boots so ``get_id(slug)`` callers resolve before the seed run re-registers
    them. Slugs absent from settings simply stay unregistered until the loader
    seeds them (the platform trigger re-runs ``server_registry.populate_ids``
    after seeding for exactly this reason).

    Resolution order for each slug:
      1. Already in registry (e.g. test setup) → skip
      2. Persisted in platform_settings (``platform.id.<slug>``) → register
    """
    from services.platform_settings_service import settings as _settings

    for slug in _all_platform_slugs():
        if slug in _registry:
            continue
        persisted = _settings.get(f"{_SETTINGS_PREFIX}{slug}")
        if persisted:
            register_id(slug, persisted)
