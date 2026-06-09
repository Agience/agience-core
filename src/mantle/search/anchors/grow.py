"""Anchor growth — admit novel signals as new anchors (RG-flow).

Canonical plan §3/§6: the AnchorSet grows as the manifold grows. A signal in a
region the anchor vocabulary doesn't yet cover (density-zoom **L0 / novel**) is a
CANDIDATE for a new anchor. :func:`propose_anchor` admits such a signal to the
live AnchorSet and persists it; a signal already covered by an anchor is
rejected (no duplication). Promotion (CANDIDATE→WORKING→CANONICAL) and decay are
the full RG-flow — future.

Non-authorizing: plaintext geometry only (canonical plan §1).
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import numpy as np

from .anchorset import CANDIDATE, L0, Anchor
from .store import (
    get_anchor_repo,
    get_crosswalks,
    get_density_zoom,
    get_live_anchorset,
    reset_anchorset,
)

logger = logging.getLogger(__name__)


def propose_anchor(
    label: str,
    vec: Sequence[float] | np.ndarray,
    *,
    model_id: Optional[str] = None,
    novel_only: bool = True,
) -> Optional[Anchor]:
    """Admit ``vec`` (labelled ``label``) as a new CANDIDATE anchor if it is
    novel — in a region the AnchorSet doesn't yet cover (density-zoom L0).

    Returns the new :class:`Anchor`, or ``None`` when there is no live AnchorSet,
    the dimension mismatches, or the signal is already covered (``novel_only``).
    A foreign ``model_id`` is projected via the cross-walk registry first.
    Persists the grown set (and refreshes the density caches so thresholds refit).
    """
    aset = get_live_anchorset()
    if aset is None or len(aset) == 0:
        return None

    v = np.asarray(vec, dtype=np.float32).ravel()
    if model_id and model_id != aset.model_id:
        v = np.asarray(
            get_crosswalks().walk(vec, model_id, aset.model_id), dtype=np.float32
        ).ravel()
    if v.shape[-1] != aset.dim:
        return None

    if novel_only:
        dz = get_density_zoom()
        if dz is not None and dz.layer(v)[0] != L0:
            return None  # already covered — not a new anchor

    anchor = Anchor.make(label, v, aset.model_id, tier=CANDIDATE)
    get_anchor_repo().add(anchor)   # persist as a vnd.agience.anchor+json artifact
    reset_anchorset()               # density refits with the new anchor on next load
    logger.info("Grew AnchorSet: +1 candidate anchor %r", label)
    return anchor
