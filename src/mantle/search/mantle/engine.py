"""MantleQueryEngine — encrypted IVF search over authorized cells.

Step 2.3 implementation. The query-time inverse of :class:`MantleIndexer`:

    query_vec ─► nearest_clusters ─► oracle.derive_cell_key ─► cell_store.get
                                                                     │
                                  unpack_cell ◄────────────────────────┘
                                       │
                                ANN within decrypted vectors
                                       │
                                dedup by (artifact_id, chunk_id)
                                       │
                                       ▼
                                    scored hits

Composes the substrate built in 2.2:

- :class:`OracleService` (2.2a) — derives cell keys; refuses keys for
  revoked grants
- :func:`cell.unpack_cell` (2.2b.i) — decrypts + deserializes
- :mod:`clustering` (2.2b.ii) — routes the query to its nearest clusters
- :class:`CellStore` + :class:`CentroidStore` (2.2b.iii) — opaque storage

Cell cache: an in-memory dict with TTL (configurable, default 60s) keeps
recently-decrypted cells around so repeat queries don't pay the crypto
cost twice. Plaintext is held only for the cache window.

See `.dev/features/mantle-mvp.md` § Layer 2c.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from . import cell as cell_mod
from .oracle import OracleService
from .stores import CellStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MantleHit:
    """One decrypted, scored hit from the MANTLE query path.

    ``score`` is cosine similarity in [-1, 1]; higher is closer. When fused
    with BM25 in the accessor (Step 2.4), it'll be fed into RRF.
    """
    artifact_id: str
    chunk_id: int
    score: float
    principal_id: str
    collection_id: str


# ---------------------------------------------------------------------------
# Cell cache
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    chunks: List[dict]
    expires_at: float


class _CellCache:
    """Thread-safe TTL cache keyed by ``(principal_id, collection_id)``.

    Trades plaintext-in-memory window against crypto round-trip cost. The
    default 60s TTL matches the MANTLE MVP spec's grant-check cache.
    """

    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        self._entries: dict[tuple[str, str, str], _CacheEntry] = {}

    def get(
        self, principal_id: str, collection_id: str, cluster_id: str = ""
    ) -> Optional[List[dict]]:
        key = (principal_id, collection_id, cluster_id)
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at < now:
                self._entries.pop(key, None)
                return None
            return entry.chunks

    def put(
        self,
        principal_id: str,
        collection_id: str,
        chunks: List[dict],
        cluster_id: str = "",
    ) -> None:
        key = (principal_id, collection_id, cluster_id)
        with self._lock:
            self._entries[key] = _CacheEntry(
                chunks=chunks, expires_at=time.time() + self._ttl
            )

    def evict(self, principal_id: str, collection_id: str, cluster_id: str = "") -> None:
        key = (principal_id, collection_id, cluster_id)
        with self._lock:
            self._entries.pop(key, None)

    def evict_context(self, principal_id: str, collection_id: str) -> None:
        """Evict every cached cluster of one ``(owner, collection)`` — an
        artifact's chunks span several anchor cells, so re-index invalidation
        must drop them all, not just one cluster."""
        with self._lock:
            stale = [
                k for k in self._entries
                if k[0] == principal_id and k[1] == collection_id
            ]
            for k in stale:
                self._entries.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# ---------------------------------------------------------------------------
# MantleQueryEngine
# ---------------------------------------------------------------------------

class MantleQueryEngine:
    """Encrypted anchor-routed ANN query path."""

    def __init__(
        self,
        oracle: OracleService,
        cell_store: Optional[CellStore] = None,
        *,
        cell_cache_ttl_s: int = 60,
        nprobe: int = 8,
    ) -> None:
        self._oracle = oracle
        self._cells = cell_store
        self._cache = _CellCache(ttl_seconds=cell_cache_ttl_s)
        self._nprobe = nprobe

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: Sequence[float],
        authorized_contexts: Iterable[Tuple[str, str]],
        *,
        top_k: int = 50,
    ) -> List[MantleHit]:
        """Run a vector search over the union of authorized cells.

        ``authorized_contexts`` is an iterable of ``(principal_id, collection_id)``
        tuples — the result of :class:`LightConeResolver`.resolve() filtered
        through the artifact ownership graph.

        For each context, fetch the routed cells, decrypt, run cosine ANN, and
        merge results. Deduplicates by ``(artifact_id, chunk_id)`` — when a
        chunk appears in multiple authorized contexts, the highest score wins.

        Returns up to ``top_k`` hits sorted by descending score.

        Raises :class:`ValueError` when ``query_embedding`` is empty or
        when the cell store isn't wired up.
        """
        if self._cells is None:
            raise ValueError(
                "MantleQueryEngine requires cell_store"
            )

        q = np.asarray(query_embedding, dtype=np.float32)
        if q.ndim != 1 or q.size == 0:
            raise ValueError("query_embedding must be a non-empty 1-D vector")
        # Normalize once — ANN uses the same metric as clustering (cosine).
        norm = float(np.linalg.norm(q))
        if norm == 0:
            raise ValueError("query_embedding has zero norm")
        q = q / norm

        contexts = list(authorized_contexts)
        if not contexts:
            return []

        if top_k <= 0:
            return []

        # Route the query to its nearest-anchor clusters (canonical plan §5.1):
        # decrypt only those cells per authorized context, not the whole union.
        # The AnchorSet is mandatory (bootstrapped from the seed corpus on first
        # use); there is one path and no flat fallback.
        from search.anchors.routing import route_query
        from search.anchors.store import require_live_anchorset

        clusters = route_query(require_live_anchorset(), q, nprobe=self._nprobe)

        # Best-score-wins dedup.
        best: dict[Tuple[str, int], MantleHit] = {}

        for principal_id, collection_id in contexts:
            if not principal_id or not collection_id:
                continue
            for cluster_id in clusters:
                chunks = self._load_cell(principal_id, collection_id, cluster_id)
                if chunks:
                    self._score_chunks(q, chunks, principal_id, collection_id, best)

        # Sort by score descending and trim.
        hits = sorted(best.values(), key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_cell(
        self, principal_id: str, collection_id: str, cluster_id: str = ""
    ) -> List[dict]:
        """Cache-aware cell fetch: return decrypted chunks or [] when unavailable.

        Cells that fail GCM authentication (wrong key, tampered) are
        treated as misses — the search continues over the remaining
        authorized cells. We don't surface CellTampered as a search-time
        error because that would let one tampered cell DoS a whole query.
        """
        cached = self._cache.get(principal_id, collection_id, cluster_id)
        if cached is not None:
            return cached

        blob = self._cells.get(principal_id, collection_id, cluster_id)
        if blob is None:
            return []

        aad = cell_mod.cell_aad(collection_id, cluster_id)
        try:
            key = self._oracle.derive_cell_key(principal_id, collection_id, cluster_id)
            chunks = cell_mod.unpack_cell(blob, key, collection_id=aad)
        except cell_mod.CellTampered:
            logger.warning(
                "Cell (%s, %s, %s) failed GCM auth — skipping in search",
                principal_id, collection_id, cluster_id,
            )
            return []
        except cell_mod.CellMalformed:
            logger.warning(
                "Cell (%s, %s, %s) is malformed — skipping in search",
                principal_id, collection_id, cluster_id,
            )
            return []

        self._cache.put(principal_id, collection_id, chunks, cluster_id)
        return chunks

    def _score_chunks(
        self,
        query: np.ndarray,
        chunks: List[dict],
        principal_id: str,
        collection_id: str,
        best: dict[Tuple[str, int], MantleHit],
    ) -> None:
        """Cosine-score every chunk in a cell against ``query``; update ``best``.

        ``query`` is already L2-normalized. Each chunk's embedding is
        normalized on the fly so cosine similarity = dot product. Cells
        whose chunks are missing embeddings are silently skipped.
        """
        for chunk in chunks:
            embedding = chunk.get("embedding")
            artifact_id = chunk.get("artifact_id")
            chunk_id = chunk.get("chunk_id")
            if embedding is None or artifact_id is None or chunk_id is None:
                continue
            try:
                vec = np.asarray(embedding, dtype=np.float32)
            except (TypeError, ValueError):
                continue
            if vec.ndim != 1 or vec.size != query.size:
                # Mismatched dimensions — skip silently rather than fail
                # the whole query.
                continue
            norm = float(np.linalg.norm(vec))
            if norm == 0:
                continue
            score = float(np.dot(query, vec / norm))

            key = (artifact_id, chunk_id)
            existing = best.get(key)
            if existing is None or score > existing.score:
                best[key] = MantleHit(
                    artifact_id=artifact_id,
                    chunk_id=chunk_id,
                    score=score,
                    principal_id=principal_id,
                    collection_id=collection_id,
                )

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def evict_cache(
        self,
        principal_id: Optional[str] = None,
        collection_id: Optional[str] = None,
    ) -> None:
        """Drop cached cells. With no args, clears the whole cache;
        with both args, evicts that one entry."""
        if principal_id is None and collection_id is None:
            self._cache.clear()
        elif principal_id and collection_id:
            self._cache.evict_context(principal_id, collection_id)
        else:
            raise ValueError(
                "evict_cache: pass either no args (clear all) or both principal_id and collection_id"
            )


__all__ = ["MantleHit", "MantleQueryEngine"]
