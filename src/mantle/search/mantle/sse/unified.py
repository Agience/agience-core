"""MantleUnifiedAccessor — RRF fusion of MANTLE vector + SSE lexical (Step 2.6.8).

The canonical search backend after OpenSearch retirement (Step 2.6.9
part 2, 2026-05-09). The two arms are:

- :class:`SseQueryEngine` — encrypted lexical (replaces OpenSearch BM25).
- :class:`MantleQueryEngine` — encrypted vector (unchanged).

Fusion uses standard Reciprocal Rank Fusion (k=60 default, matching the
existing accessor). Hits are at *artifact* granularity: MANTLE chunk hits
collapse to artifact level (best chunk score wins) before fusion, and
SSE entries are already at artifact level. The fused result is a list of
ranked ``UnifiedHit`` records that carry the underlying scores, a
provenance flag (``"sse"`` / ``"vector"`` / ``"both"``), and the owner /
collection context for downstream metadata hydration.

Because neither SSE nor MANTLE stores plaintext text (encryption-at-rest
is the whole point), the unified accessor does *not* hydrate
title/description/content here. The consumer (the search router in
2.6.9) reads those from Arango by ``artifact_id`` after fusion, the same
way it'd read any artifact's metadata. Keeping hydration outside the
accessor keeps the fusion logic pure and testable without an Arango
fixture.

See ``internal design notes`` § Query Flow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Literal, Optional, Sequence, Tuple

from ..engine import MantleHit, MantleQueryEngine
from .query import SseHit, SseQueryEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


HitSource = Literal["sse", "vector", "both"]


@dataclass(frozen=True)
class UnifiedHit:
    """One artifact-level hit produced by RRF fusion.

    ``rrf_score`` is the fused rank score (higher = better; bounded by
    the sum of the two arms' contributions ≤ 2 / (k+1)).

    ``sse_score`` and ``vector_score`` carry the raw underlying scores
    when this artifact appeared in that arm — so callers that want to
    inspect or re-rank can. Either may be ``None`` if the artifact only
    matched in one arm.

    ``source`` is a quick filter for "which arm(s) found it".
    """

    artifact_id: str
    collection_id: str
    principal_id: str
    rrf_score: float
    sse_score: Optional[float]
    vector_score: Optional[float]
    source: HitSource


# ---------------------------------------------------------------------------
# RRF fusion helpers
# ---------------------------------------------------------------------------


def _collapse_mantle_hits_to_artifact(
    mantle_hits: Sequence[MantleHit],
) -> list[MantleHit]:
    """Collapse chunk-level MantleHits to one per artifact (best score wins).

    Preserves the artifact's first-seen ``(principal_id, collection_id)``
    context — when an artifact has chunks across multiple collections in
    the authorized scope, the first occurrence's context is kept and
    subsequent collections are dropped. The unified accessor doesn't try
    to score the same artifact in N collections separately; that's an
    SSE-arm concern (lexical scores can differ per collection's
    presence) and falls out of the per-(art, col) SSE hits naturally.
    """
    best: dict[str, MantleHit] = {}
    for hit in mantle_hits:
        existing = best.get(hit.artifact_id)
        if existing is None or hit.score > existing.score:
            best[hit.artifact_id] = hit
    return list(best.values())


def _rrf_fuse(
    sse_hits: Sequence[SseHit],
    mantle_hits: Sequence[MantleHit],
    *,
    k: int = 60,
) -> list[UnifiedHit]:
    """Fuse the two arms via Reciprocal Rank Fusion.

    RRF score per artifact::

        rrf_score(art) = Σ_arms 1 / (k + rank_arm(art))

    where rank starts at 1. An artifact appearing in both arms sums
    contributions; an artifact in only one arm gets just one term.

    Inputs must already be sorted by descending arm-score; both engines
    return sorted lists by contract, so callers don't need to re-sort.
    """
    if k <= 0:
        raise ValueError(f"RRF k must be positive, got {k}")

    # Collapse MANTLE chunk hits → one per artifact.
    mantle_artifact_hits = _collapse_mantle_hits_to_artifact(mantle_hits)
    mantle_artifact_hits.sort(key=lambda h: h.score, reverse=True)

    # SSE hits are at (artifact, collection) granularity. RRF fusion is
    # per artifact, so we collapse here too — best (artifact, collection)
    # score wins. The chosen collection_id flows into UnifiedHit so
    # downstream hydration knows which collection to display the artifact
    # under.
    sse_by_artifact: dict[str, SseHit] = {}
    for hit in sse_hits:
        existing = sse_by_artifact.get(hit.artifact_id)
        if existing is None or hit.score > existing.score:
            sse_by_artifact[hit.artifact_id] = hit
    sse_artifact_hits = sorted(
        sse_by_artifact.values(), key=lambda h: h.score, reverse=True,
    )

    rrf_scores: dict[str, float] = {}
    sse_score: dict[str, float] = {}
    vector_score: dict[str, float] = {}
    contexts: dict[str, tuple[str, str]] = {}  # artifact → (owner, collection)

    for rank, hit in enumerate(sse_artifact_hits, start=1):
        rrf_scores[hit.artifact_id] = (
            rrf_scores.get(hit.artifact_id, 0.0) + 1.0 / (k + rank)
        )
        sse_score[hit.artifact_id] = hit.score
        contexts.setdefault(
            hit.artifact_id, (hit.principal_id, hit.collection_id),
        )

    for rank, hit in enumerate(mantle_artifact_hits, start=1):
        rrf_scores[hit.artifact_id] = (
            rrf_scores.get(hit.artifact_id, 0.0) + 1.0 / (k + rank)
        )
        vector_score[hit.artifact_id] = hit.score
        contexts.setdefault(
            hit.artifact_id, (hit.principal_id, hit.collection_id),
        )

    out: list[UnifiedHit] = []
    for artifact_id, fused_score in rrf_scores.items():
        principal_id, collection_id = contexts[artifact_id]
        in_sse = artifact_id in sse_score
        in_vec = artifact_id in vector_score
        source: HitSource = "both" if in_sse and in_vec else (
            "sse" if in_sse else "vector"
        )
        out.append(
            UnifiedHit(
                artifact_id=artifact_id,
                collection_id=collection_id,
                principal_id=principal_id,
                rrf_score=fused_score,
                sse_score=sse_score.get(artifact_id),
                vector_score=vector_score.get(artifact_id),
                source=source,
            )
        )

    out.sort(key=lambda h: h.rrf_score, reverse=True)
    return out


# ---------------------------------------------------------------------------
# Unified accessor
# ---------------------------------------------------------------------------


class MantleUnifiedAccessor:
    """RRF fusion of MANTLE vector + SSE lexical.

    ``mantle_engine`` may be ``None`` to run lexical-only (e.g. when a
    deployment opts out of the vector arm); ``sse_engine`` is required.
    The vector arm is also skipped when no query embedding is supplied
    to :meth:`search` — embedding is the consumer's responsibility, both
    so the accessor stays HTTP-free and so callers can choose which
    embedding model to use.

    Returns ``UnifiedHit`` records ordered by descending RRF score, ready
    for the consumer to hydrate from Arango.
    """

    def __init__(
        self,
        sse_engine: SseQueryEngine,
        mantle_engine: Optional[MantleQueryEngine] = None,
        *,
        rrf_k: int = 60,
    ) -> None:
        if rrf_k <= 0:
            raise ValueError(f"rrf_k must be positive, got {rrf_k}")
        self._sse = sse_engine
        self._mantle = mantle_engine
        self._rrf_k = rrf_k

    def search(
        self,
        query_text: str,
        authorized_contexts: Iterable[Tuple[str, str]],
        *,
        query_embedding: Optional[Sequence[float]] = None,
        top_k: int = 50,
        sse_field_overrides: Optional[Iterable[str]] = None,
        sse_top_k_multiplier: int = 3,
        mantle_top_k_multiplier: int = 3,
    ) -> list[UnifiedHit]:
        """Run both arms and fuse.

        ``authorized_contexts`` is a list of ``(principal_id, collection_id)``
        tuples from the light-cone resolver. Both engines apply the same
        scope.

        ``query_embedding`` enables the vector arm. When ``None`` (or
        when ``mantle_engine`` was not supplied at construction), the
        accessor returns SSE-only fused results.

        ``sse_top_k_multiplier`` / ``mantle_top_k_multiplier`` widen each
        arm's underlying retrieval size so RRF has enough rank diversity
        to fuse from. Default 3× (e.g., top_k=20 → each arm fetches 60).
        """
        if top_k <= 0:
            return []
        contexts = list(authorized_contexts)
        if not contexts:
            return []

        # SSE arm.
        sse_hits = self._sse.search(
            query_text, contexts,
            top_k=max(top_k * sse_top_k_multiplier, 20),
            fields=sse_field_overrides,
        )

        # Vector arm — only if engine + embedding both available.
        mantle_hits: list[MantleHit] = []
        if self._mantle is not None and query_embedding is not None:
            try:
                mantle_hits = self._mantle.search(
                    query_embedding, contexts,
                    top_k=max(top_k * mantle_top_k_multiplier, 20),
                )
            except Exception:  # noqa: BLE001 — vector-arm errors must not fail search
                logger.exception(
                    "MantleUnifiedAccessor: vector arm raised; falling back to SSE-only"
                )

        if not sse_hits and not mantle_hits:
            return []

        fused = _rrf_fuse(sse_hits, mantle_hits, k=self._rrf_k)
        return fused[:top_k]


__all__ = [
    "MantleUnifiedAccessor",
    "HitSource",
    "UnifiedHit",
]
