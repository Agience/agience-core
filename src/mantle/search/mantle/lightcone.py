"""LightConeResolver — BFS over `collection_artifacts` origin edges.

Resolves the set of artifact IDs reachable from a principal's grants by
walking ``origin: true, relationship: null`` edges outbound through
Arango, intersecting each edge's ``propagate`` mask with the requested
action.

CRUDEASIO lives in Mantle (Arango grants collection). Grants are read
directly from `db_arango.get_active_grants_for_grantee` — no Origin HTTP
calls. This keeps the resolver on the same data source as `check_access`.

After OpenSearch retirement (Step 2.6.9), this is the only ACL path —
both MANTLE-SSE lexical and MANTLE vector search consume the resolver's
authorized artifact set. The legacy flat ACL filter that lived in the
OpenSearch query builder is gone.

See `internal design notes` § Layer 1.
"""

from __future__ import annotations

from typing import Optional, Set

from db import arango as db_arango
from services.dependencies import _ACTION_FLAG_MAP


class LightConeResolver:
    """BFS over origin edges with `propagate` masks. Bounded to ``max_depth``."""

    def __init__(self, db, *, max_depth: int = 4) -> None:
        self._db = db
        self._max_depth = max_depth

    def resolve(
        self,
        principal_id: str,
        action: str = "read",
        *,
        principal_type: str = "user",
    ) -> Set[str]:
        """Return artifact IDs the principal can reach for ``action``.

        Two-step traversal:

        1. Fetch the principal's grants from Arango (grants collection). Filter
           to grants that allow ``action`` (CRUDEASIO flag check) and have a
           non-empty ``resource_id``.
        2. For each granted resource, BFS outbound through `origin: true,
           relationship: null`` edges in Arango, pruning when an edge's
           ``propagate`` mask doesn't include the action. The traversal is
           bounded by ``max_depth``.

        The returned set is the union of directly-granted IDs plus all
        descendants reachable through an unbroken chain of action-permitted
        origin edges.

        Returns an empty set when the principal has no relevant grants or
        the action name is unknown.
        """
        flag_attr: Optional[str] = _ACTION_FLAG_MAP.get(action)
        if flag_attr is None:
            return set()

        grants = db_arango.get_active_grants_for_grantee(
            self._db, grantee_id=principal_id, grantee_type=principal_type
        )
        granted_ids = [
            g.resource_id
            for g in grants
            if g.resource_id and getattr(g, flag_attr, False)
        ]
        if not granted_ids:
            return set()

        result: Set[str] = set(granted_ids)
        descendants = db_arango.list_origin_descendants(
            self._db, granted_ids, action, max_depth=self._max_depth
        )
        result.update(descendants)
        return result
