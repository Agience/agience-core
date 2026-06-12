"""In-process BM25 scorer for MANTLE-SSE (Step 2.6.5).

Standard Okapi BM25 with field boosting. After the SSE query engine
fetches and decrypts posting lists for the query's blind tokens, this
module aggregates per-(artifact, collection) scores using the corpus
stats from :mod:`stats`.

Formula (per BM25 reference, matching OpenSearch's defaults)::

    BM25(q, d) = Σ_{t in q} field_boost · IDF(t) · normalized_tf(t, d)

    IDF(t)              = ln( (N - df(t) + 0.5) / (df(t) + 0.5) + 1 )
    normalized_tf(t, d) = (tf · (k1 + 1)) /
                          (tf + k1 · (1 - b + b · dl / avgdl))

Defaults: ``k1 = 1.2``, ``b = 0.75`` (Lucene / OpenSearch BM25Similarity).

A blind token encodes ``(field, term)`` (see :mod:`blind_tokens`), so a
posting list inherently scopes to one field. The scorer takes a flat
list of "this token's entries, in this field" tuples — the query engine
constructs that list after blind-token lookup and decryption.

This module is the contained scoring piece. It depends only on
:class:`Stats` (read-only) and the entry shape — no S3, no crypto, no
storage. The query engine (Step 2.6.7) will compose this with posting
fetches; the unified accessor (Step 2.6.8) will fold its output into
RRF fusion.

See ``internal design notes`` § BM25 Scoring.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable, Mapping

from .stats import Stats

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_K1 = 1.2
DEFAULT_B = 0.75
DEFAULT_FIELD_BOOST = 1.0


# ---------------------------------------------------------------------------
# Single-term scoring primitives
# ---------------------------------------------------------------------------


def idf(df_value: int, doc_count: int) -> float:
    """Standard Lucene-style IDF:

        IDF = ln( (N - df + 0.5) / (df + 0.5) + 1 )

    Returns 0.0 when ``doc_count`` is 0 or ``df_value`` is 0 — both cases
    mean BM25 has no information about this term, so the contribution is
    nil. The ``+1`` inside the log keeps IDF non-negative even for very
    common terms (``df → N``).
    """
    if doc_count <= 0 or df_value <= 0:
        return 0.0
    numerator = doc_count - df_value + 0.5
    denominator = df_value + 0.5
    return math.log(numerator / denominator + 1.0)


def normalized_tf(
    tf: int,
    dl: int,
    avg_dl: float,
    *,
    k1: float = DEFAULT_K1,
    b: float = DEFAULT_B,
) -> float:
    """Length-normalized term frequency component of BM25.

        nf = (tf · (k1 + 1)) / (tf + k1 · (1 - b + b · dl / avgdl))

    When ``avg_dl <= 0`` (no documents have content in this field), the
    length normalization collapses to the no-normalization ratio
    (``tf · (k1 + 1) / (tf + k1)``) — equivalent to ``b = 0`` for that
    field. This matches Lucene's behavior on first-document corpora.
    """
    if tf <= 0:
        return 0.0
    if avg_dl > 0:
        norm_factor = 1.0 - b + b * (dl / avg_dl)
    else:
        norm_factor = 1.0
    denom = tf + k1 * norm_factor
    if denom <= 0:
        return 0.0
    return (tf * (k1 + 1.0)) / denom


def bm25_term_score(
    *,
    tf: int,
    dl: int,
    df_value: int,
    doc_count: int,
    avg_dl: float,
    field_boost: float = DEFAULT_FIELD_BOOST,
    k1: float = DEFAULT_K1,
    b: float = DEFAULT_B,
) -> float:
    """Compute one term's BM25 contribution (with field boost) for one
    document. Combines :func:`idf` and :func:`normalized_tf` and applies
    the field weight.

    Returns 0.0 when any input would zero the score (no term, no docs,
    no df, no tf).
    """
    if field_boost <= 0:
        return 0.0
    return (
        field_boost
        * idf(df_value, doc_count)
        * normalized_tf(tf, dl, avg_dl, k1=k1, b=b)
    )


# ---------------------------------------------------------------------------
# Aggregated query scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenHit:
    """One blind token's posting list, paired with its semantic field.

    The query engine produces a :class:`TokenHit` per ``(query_term, field)``
    combination after fetching + decrypting the posting list. The scorer
    aggregates contributions from every :class:`TokenHit` into a single
    per-document score.
    """

    blind_token: str
    field: str
    entries: list[dict]


def score_query(
    token_hits: Iterable[TokenHit],
    stats: Stats,
    *,
    field_boosts: Mapping[str, float] | None = None,
    k1: float = DEFAULT_K1,
    b: float = DEFAULT_B,
) -> dict[tuple[str, str], float]:
    """Aggregate BM25 across every token hit, return per-document scores.

    Returns ``{(artifact_id, collection_id): score}``. The same artifact
    appearing in multiple collections produces multiple entries — that's
    intentional. Deduplication (keeping the best collection's score)
    happens in the unified accessor (Step 2.6.8) after RRF fusion across
    indexes, not here.

    Per-document score::

        score(d) = Σ_{(t, f) in token_hits}
                       field_boost[f] · IDF(t) · normalized_tf(t.tf, d.dl, avgdl[f])

    Missing field boosts default to :data:`DEFAULT_FIELD_BOOST` (1.0).
    Missing ``avg_dl`` for a field falls back to 0 → no length
    normalization for that document (see :func:`normalized_tf`).
    """
    boosts = field_boosts or {}
    scores: dict[tuple[str, str], float] = {}

    for hit in token_hits:
        if not hit.entries:
            continue
        df_value = stats.df_for(hit.blind_token)
        if df_value <= 0:
            # IDF would be 0 — short-circuit the entire posting list.
            continue
        idf_value = idf(df_value, stats.doc_count)
        if idf_value <= 0:
            continue
        avg_dl = stats.average_dl(hit.field)
        boost = boosts.get(hit.field, DEFAULT_FIELD_BOOST)
        if boost <= 0:
            continue

        for entry in hit.entries:
            artifact_id = entry.get("artifact_id")
            collection_id = entry.get("collection_id")
            if not artifact_id or not collection_id:
                continue
            tf = int(entry.get("tf", 0) or 0)
            dl = int(entry.get("dl", 0) or 0)
            if tf <= 0:
                continue
            contribution = (
                boost
                * idf_value
                * normalized_tf(tf, dl, avg_dl, k1=k1, b=b)
            )
            key = (str(artifact_id), str(collection_id))
            scores[key] = scores.get(key, 0.0) + contribution

    return scores


__all__ = [
    "DEFAULT_B",
    "DEFAULT_FIELD_BOOST",
    "DEFAULT_K1",
    "TokenHit",
    "bm25_term_score",
    "idf",
    "normalized_tf",
    "score_query",
]
