"""Anchor routing — map vectors/queries to cells (cluster = routing anchor).

The AnchorSet IS the partition (canonical plan §5.1): a chunk lands in the cell
of its nearest anchor; a query fans out to its ``nprobe`` nearest anchors. Pure
geometry — no keys/auth (the §1 invariant).

There is ONE path: every vector is anchor-routed. The AnchorSet is mandatory
(``store.require_live_anchorset`` bootstraps it from the platform seed corpus on
first use and it grows as the manifold grows). There is no flat cell, no
unrouted fallback, and no legacy partition — a vector that cannot be placed
against the anchors (empty set, dimension mismatch) is an error, not a second
path.
"""

from __future__ import annotations

from typing import List, Sequence

import numpy as np

from .anchorset import AnchorSet


def route_vector(anchorset: AnchorSet, vec: Sequence[float] | np.ndarray) -> str:
    """Cluster id (anchor_id) of the cell this vector indexes into — its nearest
    anchor.

    Raises :class:`ValueError` when the AnchorSet cannot place the vector (empty
    set or embedding/anchor dimension mismatch). There is no flat fallback.
    """
    near = anchorset.nearest(vec, k=1)
    if not near:
        raise ValueError(
            "route_vector: AnchorSet produced no nearest anchor "
            "(empty AnchorSet or embedding/anchor dimension mismatch)"
        )
    return near[0][0].anchor_id


def route_query(
    anchorset: AnchorSet,
    vec: Sequence[float] | np.ndarray,
    *,
    nprobe: int = 8,
) -> List[str]:
    """Candidate cluster ids (nearest anchors) a query must search. The nearest
    anchor — the cell a matching item would index into — is always first.

    Raises :class:`ValueError` when the AnchorSet cannot place the query (empty
    set or embedding/anchor dimension mismatch). There is no flat fallback.
    """
    near = anchorset.nearest(vec, k=max(1, nprobe))
    if not near:
        raise ValueError(
            "route_query: AnchorSet produced no nearest anchor "
            "(empty AnchorSet or embedding/anchor dimension mismatch)"
        )
    return [a.anchor_id for a, _ in near]
