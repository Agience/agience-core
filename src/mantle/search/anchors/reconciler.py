"""Reconciler — any source embedding → the native language of meaning.

See `.dev/features/mantle-canonical-architecture.md` §4. The native code is a
**sparse anchor-relative** representation: an item is its top-``m`` affinities to
the anchors. Model-unbiased (coordinate k means "closeness to anchor-concept k"
regardless of which model produced the raw vector) and dimension-agnostic (the
code lives in anchor space, not the source model's native dim) — which is why a
single index holds vectors from any embedder/modality.

INVARIANT (§1): geometry only — no keys/auth. Runs before partition/routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from .anchorset import AnchorSet


@dataclass
class SparseCode:
    """A native-language vector: ``weights`` over the anchor ``indices``,
    L2-normalized over the active set. ``dim`` is the current anchor count K."""

    indices: np.ndarray   # int positions into the AnchorSet
    weights: np.ndarray   # float32, unit-norm over the active set
    dim: int
    anchor_ids: List[str]

    def __len__(self) -> int:
        return int(self.indices.shape[0])

    @property
    def top_anchor_id(self) -> Optional[str]:
        """The routing anchor — the cell this item lands in (§5.1)."""
        return self.anchor_ids[0] if self.anchor_ids else None

    def dot(self, other: "SparseCode") -> float:
        """Cosine similarity between two native codes (both unit-norm)."""
        if len(self) == 0 or len(other) == 0:
            return 0.0
        lut = {int(i): float(w) for i, w in zip(self.indices, self.weights)}
        return float(sum(float(w) * lut.get(int(i), 0.0)
                         for i, w in zip(other.indices, other.weights)))

    def to_dict(self) -> dict:
        """JSON-serializable form for the cell chunk record (plain ints/floats)."""
        return {
            "i": [int(x) for x in self.indices],
            "w": [float(x) for x in self.weights],
            "ids": list(self.anchor_ids),
            "k": int(self.dim),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SparseCode":
        return cls(
            indices=np.asarray(d.get("i", []), dtype=int),
            weights=np.asarray(d.get("w", []), dtype=np.float32),
            dim=int(d.get("k", 0)),
            anchor_ids=list(d.get("ids", [])),
        )


class Reconciler:
    """Project source embeddings into the native language over an AnchorSet."""

    def __init__(
        self,
        anchorset: AnchorSet,
        *,
        top_m: int = 32,
        min_affinity: float = 0.0,
        crosswalks=None,
    ) -> None:
        self.anchorset = anchorset
        self.top_m = int(top_m)
        self.min_affinity = float(min_affinity)
        self.crosswalks = crosswalks   # CrosswalkRegistry | None (AlignmentRegistry)

    def to_native(
        self,
        vec: Sequence[float] | np.ndarray,
        *,
        model_id: Optional[str] = None,
    ) -> SparseCode:
        """Reconcile one source vector to a sparse anchor-relative code.

        A ``model_id`` other than the AnchorSet's is projected into the AnchorSet
        space via the cross-walk registry (AlignmentRegistry, §4.3). Without a
        registered cross-walk we fail loudly rather than silently mis-project.
        """
        if model_id is not None and model_id != self.anchorset.model_id:
            if self.crosswalks is None:
                raise ValueError(
                    f"cross-walk required: {model_id!r} → {self.anchorset.model_id!r} "
                    "(no AlignmentRegistry configured)"
                )
            vec = self.crosswalks.walk(vec, model_id, self.anchorset.model_id)

        near = self.anchorset.nearest(vec, k=self.top_m)
        near = [(a, s) for a, s in near if s >= self.min_affinity]
        if not near:
            return SparseCode(np.empty(0, dtype=int), np.empty(0, dtype=np.float32),
                              len(self.anchorset), [])

        idx = np.fromiter((self.anchorset.position(a.anchor_id) for a, _ in near),
                          dtype=int, count=len(near))
        w = np.array([max(s, 0.0) for _, s in near], dtype=np.float32)
        norm = float(np.linalg.norm(w))
        if norm > 0.0:
            w = w / norm
        return SparseCode(idx, w, len(self.anchorset), [a.anchor_id for a, _ in near])
