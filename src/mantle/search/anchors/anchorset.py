"""AnchorSet — the shared coordinate system, routing centroids, and grounding.

See `.dev/features/mantle-canonical-architecture.md` §3 (the AnchorSet is one
object: commons verified anchor ontology == MANTLE routing centroids ==
Beacon-LLM grounding) and §4 (the native language derived from it).

The AnchorSet is the FACET-commons verified anchor ontology realized in MANTLE:
a growing, layered (L0/L1/L2) set of fully-disclosed reference points. Routing
is by *nearest anchor* — the anchors ARE the centroids; there is no separate
k-means partition.

INVARIANT (§1): geometry only. Operates on plaintext vectors; never touches
cell keys / light-cone / oracle / ledger.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Fixed namespace so an anchor's artifact id is a *deterministic* UUID of its
# content — same anchor content → same id everywhere (idempotent creation,
# stable cell-routing id across rebuilds). The sha256 content-hash is the
# address; the UUID5 of it is the artifact ``_key`` (a valid UUID, as the
# artifact model expects).
_ANCHOR_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "anchors.agience.ai")

# Density-zoom LAYERS (classify an *item* by density, §6): L0 novel/sparse …
# L2 common/dense. Used by density.py. Distinct from anchor tiers below.
L0, L1, L2 = "L0", "L1", "L2"

# Anchor lifecycle TIERS (RG-flow / Beacon-LLM registry): a new anchor enters as
# CANDIDATE (a novel — density-L0 — signal), proves out to WORKING, and a
# high-mass one becomes CANONICAL. (Note the inversion: a density-L0 *item*
# becomes a CANDIDATE *anchor*.)
CANDIDATE, WORKING, CANONICAL = "candidate", "working", "canonical"


def l2norm(v: np.ndarray) -> np.ndarray:
    """Unit-normalize along the last axis (zero-safe)."""
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.clip(n, 1e-12, None)


@dataclass
class Anchor:
    """A fully-disclosed reference point — **an artifact** (canonical model:
    everything is an artifact). ``anchor_id`` is the artifact id (a deterministic
    UUID of ``content_hash``); the embedding and the rest live in the artifact's
    ``context`` (see :meth:`to_context` / :meth:`from_context`).

    Field set is superset-compatible with the facet-commons anchor record and
    Beacon-LLM's ``Anchor``. ``embedding`` is dense, unit-norm, and lives in the
    ``model_id`` space (anchors are per-model; cross-walks bridge models).
    """

    anchor_id: str
    label: str
    embedding: np.ndarray
    model_id: str
    type_id: str = "text/plain"
    tier: str = WORKING
    placed_frame: int = 0
    status: str = "active"
    content_hash: str = ""

    @staticmethod
    def make(
        label: str,
        embedding: Sequence[float] | np.ndarray,
        model_id: str,
        *,
        type_id: str = "text/plain",
        tier: str = WORKING,
        placed_frame: int = 0,
    ) -> "Anchor":
        """Content-address the anchor over (label, model_id, embedding); the
        artifact id is a deterministic UUID5 of that hash."""
        emb = l2norm(np.asarray(embedding, dtype=np.float32).ravel())
        h = hashlib.sha256()
        h.update(b"agience/anchor/v1")
        h.update(label.encode("utf-8"))
        h.update(model_id.encode("utf-8"))
        h.update(emb.tobytes())
        content_hash = h.hexdigest()
        return Anchor(
            anchor_id=str(uuid.uuid5(_ANCHOR_NS, content_hash)),
            label=label,
            embedding=emb,
            model_id=model_id,
            type_id=type_id,
            tier=tier,
            placed_frame=placed_frame,
            content_hash=content_hash,
        )

    # ------------------------------------------------------------------ artifact form
    def to_context(self) -> dict:
        """The anchor as an artifact ``context`` dict (embedding as a float list)."""
        return {
            "label": self.label,
            "embedding": self.embedding.astype(float).tolist(),
            "model_id": self.model_id,
            "content_hash": self.content_hash,
            "type_id": self.type_id,
            "tier": self.tier,
            "status": self.status,
            "placed_frame": int(self.placed_frame),
        }

    @classmethod
    def from_context(cls, anchor_id: str, ctx: dict) -> "Anchor":
        """Rebuild an Anchor from an artifact id + its ``context`` dict."""
        return cls(
            anchor_id=anchor_id,
            label=ctx.get("label", ""),
            embedding=l2norm(np.asarray(ctx.get("embedding", []), dtype=np.float32)),
            model_id=ctx.get("model_id", ""),
            type_id=ctx.get("type_id", "text/plain"),
            tier=ctx.get("tier", WORKING),
            status=ctx.get("status", "active"),
            placed_frame=int(ctx.get("placed_frame", 0)),
            content_hash=ctx.get("content_hash", ""),
        )


class AnchorSet:
    """A growing set of anchors in one model space.

    Routing/encoding use a cached ``(K, dim)`` unit-norm matrix. Small enough to
    keep in memory; the set grows continuously (§3) — there is no fixed K.
    """

    def __init__(self, model_id: str, dim: int) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.model_id = model_id
        self.dim = int(dim)
        self._anchors: List[Anchor] = []
        self._ids: set[str] = set()
        self._matrix: Optional[np.ndarray] = None  # (K, dim), unit-norm

    # ------------------------------------------------------------------ basics
    def __len__(self) -> int:
        return len(self._anchors)

    @property
    def anchors(self) -> List[Anchor]:
        return list(self._anchors)

    @property
    def matrix(self) -> Optional[np.ndarray]:
        return self._matrix

    def _rebuild(self) -> None:
        self._matrix = (
            np.vstack([a.embedding for a in self._anchors]).astype(np.float32)
            if self._anchors
            else None
        )

    # --------------------------------------------------------------- mutation
    def add(self, anchor: Anchor) -> Anchor:
        if anchor.embedding.shape[-1] != self.dim:
            raise ValueError(
                f"anchor dim {anchor.embedding.shape[-1]} != AnchorSet dim {self.dim}"
            )
        if anchor.model_id != self.model_id:
            raise ValueError(
                f"anchor model {anchor.model_id!r} != AnchorSet model {self.model_id!r} "
                "(cross-walk required — AlignmentRegistry)"
            )
        if anchor.anchor_id in self._ids:  # content-addressed idempotency
            return anchor
        self._anchors.append(anchor)
        self._ids.add(anchor.anchor_id)
        self._rebuild()
        return anchor

    def add_text(
        self,
        label: str,
        embedding: Sequence[float] | np.ndarray,
        *,
        tier: str = WORKING,
        type_id: str = "text/plain",
        placed_frame: int = 0,
    ) -> Anchor:
        return self.add(
            Anchor.make(
                label, embedding, self.model_id,
                type_id=type_id, tier=tier, placed_frame=placed_frame,
            )
        )

    # --------------------------------------------------------------- queries
    def nearest(self, vec: Sequence[float] | np.ndarray, k: int = 8) -> List[Tuple[Anchor, float]]:
        """Top-``k`` anchors by cosine. Routing = nearest anchor(s)."""
        if self._matrix is None or k < 1:
            return []
        q = l2norm(np.asarray(vec, dtype=np.float32).ravel())
        if q.shape[-1] != self.dim:
            # Dimension mismatch (a different embedder / wrong model): the vector
            # cannot be placed against the anchors. Return empty — routing
            # surfaces this as an error (no flat fallback); density/grow treat it
            # as "unplaced".
            return []
        sims = self._matrix @ q
        k = min(k, len(self._anchors))
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
        return [(self._anchors[int(i)], float(sims[int(i)])) for i in idx]

    def position(self, anchor_id: str) -> int:
        for i, a in enumerate(self._anchors):
            if a.anchor_id == anchor_id:
                return i
        raise KeyError(anchor_id)

    # ------------------------------------------------------------- bootstrap
    def bootstrap(
        self,
        items: Sequence[Tuple[str, Sequence[float] | np.ndarray]],
        k: int,
        *,
        tier: str = WORKING,
        iters: int = 25,
        seed: int = 0,
        placed_frame: int = 0,
    ) -> "AnchorSet":
        """Light-training bootstrap: cluster ``items`` (label, vec) into ``k``
        groups and admit the **medoid** (nearest real item to each cluster
        center) of each as an anchor. Real items, not synthetic centers — anchors
        are fully-disclosed artifacts (§3). Deterministic given ``seed``.
        """
        if not items:
            return self
        labels = [lab for lab, _ in items]
        X = l2norm(np.vstack([np.asarray(v, dtype=np.float32).ravel() for _, v in items]))
        if X.shape[1] != self.dim:
            raise ValueError(f"item dim {X.shape[1]} != AnchorSet dim {self.dim}")
        k = min(k, len(items))
        centers = _kmeans_cosine(X, k, iters=iters, seed=seed)
        for c in centers:
            j = int(np.argmax(X @ c))  # medoid: nearest real item to the center
            self.add_text(labels[j], X[j], tier=tier, placed_frame=placed_frame)
        return self

    # ------------------------------------------------------------- persistence
    def save(self, path: str | Path) -> None:
        """JSON dump (commons-aligned-ish). Embeddings as float lists."""
        payload = {
            "model_id": self.model_id,
            "dim": self.dim,
            "anchors": [
                {
                    "anchor_id": a.anchor_id,
                    "label": a.label,
                    "model_id": a.model_id,
                    "type_id": a.type_id,
                    "tier": a.tier,
                    "placed_frame": a.placed_frame,
                    "status": a.status,
                    "embedding": a.embedding.astype(float).tolist(),
                }
                for a in self._anchors
            ],
        }
        Path(path).write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "AnchorSet":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        s = cls(model_id=data["model_id"], dim=int(data["dim"]))
        for a in data.get("anchors", []):
            s.add(
                Anchor(
                    anchor_id=a["anchor_id"],
                    label=a["label"],
                    embedding=l2norm(np.asarray(a["embedding"], dtype=np.float32)),
                    model_id=a["model_id"],
                    type_id=a.get("type_id", "text/plain"),
                    tier=a.get("tier", WORKING),
                    placed_frame=int(a.get("placed_frame", 0)),
                    status=a.get("status", "active"),
                )
            )
        return s


def _kmeans_cosine(X: np.ndarray, k: int, *, iters: int = 25, seed: int = 0) -> np.ndarray:
    """Tiny deterministic spherical k-means (cosine). Returns ``(k, dim)``
    unit-norm centers. k-means++ init on cosine distance."""
    rng = np.random.default_rng(seed)
    n = len(X)
    first = int(rng.integers(n))
    centers = [X[first]]
    d2 = 1.0 - (X @ centers[0])
    for _ in range(1, k):
        probs = np.clip(d2, 0.0, None)
        total = float(probs.sum())
        if total <= 0.0:
            centers.append(X[int(rng.integers(n))])
        else:
            r = float(rng.random()) * total
            j = int(np.searchsorted(np.cumsum(probs), r))
            centers.append(X[min(j, n - 1)])
        d2 = np.minimum(d2, 1.0 - (X @ centers[-1]))
    C = l2norm(np.vstack(centers))
    for _ in range(iters):
        assign = np.argmax(X @ C.T, axis=1)
        new = []
        for c in range(len(C)):
            pts = X[assign == c]
            new.append(l2norm(pts.mean(0)) if len(pts) else C[c])
        C = np.vstack(new).astype(np.float32)
    return C
