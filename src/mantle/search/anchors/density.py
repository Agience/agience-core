"""Density-zoom — frame-invariant novelty layer over the AnchorSet.

Canonical plan §6. An item's *coverage* by the anchor vocabulary — its
nearest-anchor cosine affinity — places it on a discrete layer:

    L2  common/dense    (well inside the covered manifold)
    L1  working
    L0  novel/sparse    (far from every anchor → an anchor candidate; RG-flow)

Thresholds are **data-driven** from the distribution of anchor nearest-neighbour
affinities (the manifold's own spacing) — no magic constant — and cosine-based,
so the layer is frame-invariant (a gauge change / different model leaves it
unchanged). Non-authorizing: plaintext geometry only (canonical plan §1).
"""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

from .anchorset import L0, L1, L2, AnchorSet


class DensityZoom:
    """Maps a vector to its density layer over a fitted AnchorSet."""

    def __init__(self, anchorset: AnchorSet) -> None:
        self.anchorset = anchorset
        self._t_low, self._t_high = self._fit(anchorset)

    @staticmethod
    def _fit(anchorset: AnchorSet) -> Tuple[float, float]:
        """Derive (L0|L1, L1|L2) thresholds from the anchors' own spacing:
        each anchor's nearest-other-anchor cosine. An item closer to an anchor
        than anchors typically are to each other is "covered" (L2); much farther
        is novel (L0)."""
        matrix = anchorset.matrix
        if matrix is None or len(anchorset) < 3:
            return 0.0, 1.0
        sims = matrix @ matrix.T
        np.fill_diagonal(sims, -np.inf)
        nn = sims.max(axis=1)
        nn = nn[np.isfinite(nn)]
        if nn.size == 0:
            return 0.0, 1.0
        t_low = float(np.percentile(nn, 10))
        t_high = float(np.median(nn))
        if t_high <= t_low:
            t_high = t_low + 1e-3
        return t_low, t_high

    def density(self, vec: Sequence[float] | np.ndarray) -> float:
        """Nearest-anchor cosine affinity — the coverage/density proxy in [-1, 1].
        Returns 0.0 when the vector can't be placed (dim mismatch / no anchors)."""
        near = self.anchorset.nearest(vec, k=1)
        return float(near[0][1]) if near else 0.0

    def layer(self, vec: Sequence[float] | np.ndarray) -> Tuple[str, float]:
        """Return ``(layer, density)`` for ``vec``."""
        a = self.density(vec)
        if a >= self._t_high:
            return L2, a
        if a >= self._t_low:
            return L1, a
        return L0, a
