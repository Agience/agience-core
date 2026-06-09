"""AnchorRepo — the AnchorSet's persistence as artifacts.

An anchor **is an artifact** (`vnd.agience.anchor+json`); the **AnchorSet is a
collection** of them (slug ``agience-anchorset``). The geometry layer loads
anchors by a **direct, non-authorizing Arango read** (canonical plan §1: no cell
keys, no light-cone, no oracle — anchors are public geometry), builds the
in-memory :class:`AnchorSet`, and caches it. There is no JSON-file store.

Two implementations:
- :class:`ArangoAnchorRepo` — production; backs onto the artifact store.
- :class:`InMemoryAnchorRepo` — tests; keeps the geometry suite db-free.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional, Protocol

from .anchorset import Anchor, AnchorSet

logger = logging.getLogger(__name__)

# Provenance for platform-created anchor artifacts. `created_by` is provenance
# only (no access, no ownership — Phase 1 decoupled cell keys from it).
_ANCHOR_CREATED_BY = "agience-mantle"


class AnchorRepo(Protocol):
    """Persistence boundary for the AnchorSet."""

    def load(self) -> Optional[AnchorSet]:
        """Build the live AnchorSet from stored anchors, or ``None`` if empty."""

    def add(self, anchor: Anchor) -> None:
        """Persist one anchor artifact (idempotent on the anchor's id)."""

    def bulk_add(self, anchors: List[Anchor]) -> None:
        """Persist many anchors (best-effort per anchor)."""

    def count(self) -> int:
        """Number of stored anchors."""


def _build_anchorset(anchors: List[Anchor]) -> Optional[AnchorSet]:
    """Assemble an :class:`AnchorSet` from anchors (first one fixes model/dim)."""
    if not anchors:
        return None
    aset = AnchorSet(model_id=anchors[0].model_id, dim=anchors[0].embedding.shape[-1])
    for a in anchors:
        try:
            aset.add(a)
        except ValueError:
            # dim/model mismatch — a foreign-model anchor slipped in; skip it
            # rather than corrupt the set (cross-walks bridge models elsewhere).
            logger.debug("AnchorRepo: skipped anchor %s (model/dim mismatch)", a.label)
    return aset if len(aset) else None


# ---------------------------------------------------------------------------
# In-memory (tests)
# ---------------------------------------------------------------------------

class InMemoryAnchorRepo:
    """Dict-backed AnchorRepo — keeps the geometry tests db-free."""

    def __init__(self) -> None:
        self._anchors: dict[str, Anchor] = {}

    def load(self) -> Optional[AnchorSet]:
        return _build_anchorset(list(self._anchors.values()))

    def add(self, anchor: Anchor) -> None:
        self._anchors[anchor.anchor_id] = anchor  # idempotent on id

    def bulk_add(self, anchors: List[Anchor]) -> None:
        for a in anchors:
            self.add(a)

    def count(self) -> int:
        return len(self._anchors)


# ---------------------------------------------------------------------------
# Arango (production)
# ---------------------------------------------------------------------------

class ArangoAnchorRepo:
    """Backs the AnchorSet onto the artifact store: anchors are
    ``vnd.agience.anchor+json`` artifacts in the ``agience-anchorset`` collection.

    Loading is a direct read (non-authorizing) — the geometry layer never goes
    through the light-cone or the oracle.
    """

    def __init__(self, db) -> None:
        self._db = db

    def _collection_id(self) -> Optional[str]:
        from services.bootstrap_types import ANCHORSET_COLLECTION_SLUG
        from services.platform_topology import get_id_optional
        return get_id_optional(ANCHORSET_COLLECTION_SLUG)

    def load(self) -> Optional[AnchorSet]:
        cid = self._collection_id()
        if not cid:
            return None
        from db import arango as db_arango
        from services.bootstrap_types import ANCHOR_CONTENT_TYPE
        try:
            docs = db_arango.list_collection_artifacts(self._db, cid)
        except Exception:
            logger.warning("AnchorRepo: failed listing AnchorSet %s", cid, exc_info=True)
            return None
        anchors: List[Anchor] = []
        for d in docs:
            if d.get("content_type") != ANCHOR_CONTENT_TYPE:
                continue
            ctx = d.get("context")
            if isinstance(ctx, str):
                try:
                    ctx = json.loads(ctx)
                except (TypeError, ValueError):
                    continue
            if not isinstance(ctx, dict):
                continue
            aid = d.get("root_id") or d.get("id") or d.get("_key")
            if not aid:
                continue
            try:
                anchors.append(Anchor.from_context(str(aid), ctx))
            except Exception:
                logger.debug("AnchorRepo: skipped malformed anchor doc %s", aid)
        return _build_anchorset(anchors)

    def add(self, anchor: Anchor) -> None:
        cid = self._collection_id()
        if not cid:
            raise RuntimeError(
                "AnchorSet collection not seeded (slug agience-anchorset)"
            )
        from db import arango as db_arango
        from entities.artifact import Artifact
        from services.bootstrap_types import ANCHOR_CONTENT_TYPE

        # Idempotent: deterministic id means re-adding the same anchor is a no-op
        # on the doc; we still ensure the membership edge.
        exists = False
        try:
            exists = db_arango.get_artifact(self._db, anchor.anchor_id) is not None
        except Exception:
            exists = False
        if not exists:
            artifact = Artifact(
                id=anchor.anchor_id,
                root_id=anchor.anchor_id,
                collection_id=cid,
                content="",
                context=json.dumps(anchor.to_context(), separators=(",", ":")),
                state=Artifact.STATE_COMMITTED,
                created_by=_ANCHOR_CREATED_BY,
                name=anchor.label,
                content_type=ANCHOR_CONTENT_TYPE,
            )
            db_arango.create_artifact(self._db, artifact)
        db_arango.add_artifact_to_collection(self._db, cid, anchor.anchor_id, origin=True)

    def bulk_add(self, anchors: List[Anchor]) -> None:
        for a in anchors:
            try:
                self.add(a)
            except Exception:
                logger.warning("AnchorRepo: failed adding anchor %s", a.label, exc_info=True)

    def count(self) -> int:
        aset = self.load()
        return len(aset) if aset else 0
