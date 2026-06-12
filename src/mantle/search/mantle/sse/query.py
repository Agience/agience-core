"""SseQueryEngine — blind-token lookup + BM25 scoring (Step 2.6.7).

The query-time inverse of :class:`SseIndexer`. Composes:

- :class:`OracleService` — derives owner SSE keys
- :mod:`tokenizer` — same analysis pipeline as index time (must match)
- :mod:`blind_tokens` — per-owner / per-field / per-term blind tokens
- :class:`PostingStore` + :class:`StatsStore` — opaque storage
- :mod:`posting` — decrypts posting lists, decrypts manifests (unused
  here — the deletion path consumes those)
- :mod:`stats` — decrypts corpus stats
- :mod:`scorer` — BM25 with field boosting

Path:

    query (text)
        ▼
    tokenize → list of stems
        ▼
    group authorized_contexts by owner
        ▼
    for each owner:
        decrypt corpus stats
        for each (stem × field):
            generate blind_token via owner_sse_key
            fetch + decrypt posting list
            filter entries to authorized collection set for this owner
            construct TokenHit
        score_query(token_hits, stats, field_boosts) → per-doc scores
    merge across owners → sort by score → top_k

Caching:

- Per-(owner, blind_token) posting list cache (TTL — default 60s).
  Trades plaintext-in-memory window against re-fetch + re-decrypt cost.
- Per-owner corpus stats cache (TTL — default 60s).

Stats and posting lists that fail GCM authentication are treated as
cache misses, *not* surfaced as search-time errors. One tampered blob
must not DoS a whole query.

Per-field search budget: by default the engine searches all four
indexed fields (title, description, tags, content) per query term. The
``field_boosts`` constructor argument controls which fields to score
(missing or zero boost → field skipped) and the per-field BM25 weight.

Wildcard / prefix queries: not in this MVP. The indexer pre-computes
prefix tokens (px3/px4/px5 for title and tags), and a future query path
extension will detect ``term*`` syntax and look up the matching prefix
blind token. For now :meth:`search` does exact-stem lookup only.

Constant-width batch padding (per MANTLE-SSE spec § Access Pattern
Privacy): not in this MVP. With the in-memory store the storage layer
is trusted; with the S3-backed store this becomes relevant for log-
based traffic analysis. Padding can be added by extending the lookup
loop with random authorized decoy tokens — pure privacy enhancement,
no correctness impact.

See ``internal design notes`` § Query Flow.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Tuple

from . import posting as posting_mod
from . import stats as stats_mod
from .blind_tokens import (
    FIELD_CONTENT,
    FIELD_DESCRIPTION,
    FIELD_TAGS,
    FIELD_TITLE,
    blind_token,
)
from .posting import PostingStore
from .scorer import (
    DEFAULT_B,
    DEFAULT_FIELD_BOOST,
    DEFAULT_K1,
    TokenHit,
    score_query,
)
from .stats import Stats, StatsStore
from .tokenizer import bigrams as _stem_bigrams, tokenize
from ..oracle import OracleService

logger = logging.getLogger(__name__)


# Long-form (BM25) ↔ short-form (blind-token API).
_LONG_TO_SHORT = {
    "title": FIELD_TITLE,
    "description": FIELD_DESCRIPTION,
    "tags": FIELD_TAGS,
    "content": FIELD_CONTENT,
}

_DEFAULT_FIELDS: tuple[str, ...] = ("title", "description", "tags", "content")
_DEFAULT_CACHE_TTL_S = 60


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SseHit:
    """One BM25-scored hit from the SSE query path.

    The unified accessor (Step 2.6.8) folds these into RRF alongside
    MantleHit (vector). Higher score = better — same convention as
    MantleHit.
    """

    artifact_id: str
    collection_id: str
    principal_id: str
    score: float


# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------


@dataclass
class _CachedPosting:
    entries: list[dict]
    expires_at: float


@dataclass
class _CachedStats:
    stats: Stats
    expires_at: float


class _PostingCache:
    """Thread-safe TTL cache keyed by ``(principal_id, blind_token)``."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        self._entries: dict[tuple[str, str], _CachedPosting] = {}

    def get(self, principal_id: str, blind_token: str) -> Optional[list[dict]]:
        key = (principal_id, blind_token)
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at < now:
                self._entries.pop(key, None)
                return None
            return entry.entries

    def put(self, principal_id: str, blind_token: str, entries: list[dict]) -> None:
        key = (principal_id, blind_token)
        with self._lock:
            self._entries[key] = _CachedPosting(
                entries=entries, expires_at=time.time() + self._ttl,
            )

    def invalidate_owner(self, principal_id: str) -> None:
        with self._lock:
            self._entries = {
                k: v for k, v in self._entries.items() if k[0] != principal_id
            }


class _StatsCache:
    """Thread-safe TTL cache keyed by ``principal_id``."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        self._entries: dict[str, _CachedStats] = {}

    def get(self, principal_id: str) -> Optional[Stats]:
        now = time.time()
        with self._lock:
            entry = self._entries.get(principal_id)
            if entry is None:
                return None
            if entry.expires_at < now:
                self._entries.pop(principal_id, None)
                return None
            return entry.stats

    def put(self, principal_id: str, stats: Stats) -> None:
        with self._lock:
            self._entries[principal_id] = _CachedStats(
                stats=stats, expires_at=time.time() + self._ttl,
            )

    def invalidate(self, principal_id: str | None = None) -> None:
        with self._lock:
            if principal_id is None:
                self._entries.clear()
            else:
                self._entries.pop(principal_id, None)


# ---------------------------------------------------------------------------
# Query engine
# ---------------------------------------------------------------------------


class SseQueryEngine:
    """Encrypted lexical query path."""

    def __init__(
        self,
        oracle: OracleService,
        posting_store: PostingStore,
        stats_store: StatsStore,
        *,
        field_boosts: Optional[Mapping[str, float]] = None,
        cache_ttl_s: int = _DEFAULT_CACHE_TTL_S,
        k1: float = DEFAULT_K1,
        b: float = DEFAULT_B,
    ) -> None:
        self._oracle = oracle
        self._postings = posting_store
        self._stats = stats_store
        self._field_boosts: dict[str, float] = dict(field_boosts or {})
        self._k1 = k1
        self._b = b
        self._posting_cache = _PostingCache(cache_ttl_s)
        self._stats_cache = _StatsCache(cache_ttl_s)

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        authorized_contexts: Iterable[Tuple[str, str]],
        *,
        top_k: int = 50,
        fields: Optional[Iterable[str]] = None,
    ) -> list[SseHit]:
        """Run a lexical search over the authorized scope.

        ``query`` — raw user query text. Tokenized + stemmed with the
        same pipeline the indexer used.

        ``authorized_contexts`` — iterable of ``(principal_id, collection_id)``
        tuples from the light-cone resolver. The query engine groups by
        owner and filters posting list entries down to each owner's
        authorized collection set before scoring.

        ``fields`` — optional override of which long-form fields to
        search. Default: all four indexed fields. Fields with zero or
        negative boost are skipped regardless. Fields not in
        :data:`_LONG_TO_SHORT` are silently ignored.

        ``top_k`` — maximum number of hits returned. Returns fewer if
        the corpus is smaller. ``top_k <= 0`` short-circuits to ``[]``.
        """
        if top_k <= 0:
            return []
        if not query or not query.strip():
            return []

        # Detect phrase query: leading + trailing double-quotes signal exact
        # phrase matching. Strip quotes before tokenizing so stems reflect
        # the actual phrase terms (not quote characters).
        is_phrase = len(query) > 2 and query[0] == '"' and query[-1] == '"'
        if is_phrase:
            query = query[1:-1]

        stems = tokenize(query)
        if not stems:
            return []

        target_fields = self._resolve_fields(fields)
        if not target_fields:
            return []

        # Group authorized contexts by owner.
        scope: dict[str, set[str]] = {}
        for principal_id, collection_id in authorized_contexts:
            if not principal_id or not collection_id:
                continue
            scope.setdefault(principal_id, set()).add(collection_id)
        if not scope:
            return []

        # Score per owner; merge into a flat list.
        all_hits: list[SseHit] = []
        for principal_id, collection_ids in scope.items():
            hits = self._score_owner(
                principal_id, collection_ids, stems, target_fields,
                is_phrase=is_phrase,
            )
            all_hits.extend(hits)

        # Sort by score desc and trim to top_k. We do *not* dedup
        # across (artifact_id, collection_id) here — the unified
        # accessor (2.6.8) handles cross-collection collapsing after
        # RRF fusion across indexes.
        all_hits.sort(key=lambda h: h.score, reverse=True)
        return all_hits[:top_k]

    def invalidate_caches(self, principal_id: Optional[str] = None) -> None:
        """Drop cached posting lists + stats. Pass ``principal_id`` to
        invalidate one owner; omit to clear everything.

        The indexer doesn't auto-invalidate this cache today; production
        wiring (Step 2.6.9) will call this after each commit so query
        results stay fresh."""
        if principal_id is None:
            self._posting_cache = _PostingCache(self._posting_cache._ttl)
            self._stats_cache.invalidate()
        else:
            self._posting_cache.invalidate_owner(principal_id)
            self._stats_cache.invalidate(principal_id)

    # ------------------------------------------------------------------
    # Per-owner scoring
    # ------------------------------------------------------------------

    def _score_owner(
        self,
        principal_id: str,
        authorized_collections: set[str],
        stems: list[str],
        target_fields: list[str],
        *,
        is_phrase: bool = False,
    ) -> list[SseHit]:
        owner_sse_key = self._oracle.derive_sse_key(principal_id)

        # Decrypt corpus stats — without these BM25 has no IDF.
        owner_stats = self._load_stats(principal_id, owner_sse_key)
        if owner_stats is None:
            return []

        # Phrase queries: resolve the bigram gate FIRST so that the
        # unigram scoring pass only touches the documents that actually
        # contain the phrase. This mirrors how Typesense handles phrase
        # search — the n-gram posting list is the gate; unigram BM25
        # runs only on survivors. One index scan, not two.
        phrase_ids: Optional[set[str]] = None
        if is_phrase and len(stems) >= 2:
            bigram_sets: list[set[str]] = []
            for bigram in _stem_bigrams(stems):
                bigram_ids: set[str] = set()
                for field_long in target_fields:
                    bt = blind_token(
                        owner_sse_key, _LONG_TO_SHORT[field_long], bigram,
                    )
                    for entry in self._load_posting(principal_id, owner_sse_key, bt):
                        if entry.get("collection_id") in authorized_collections:
                            art_id = entry.get("artifact_id", "")
                            if art_id:
                                bigram_ids.add(art_id)
                if not bigram_ids:
                    # Any bigram missing → phrase cannot exist in corpus.
                    return []
                bigram_sets.append(bigram_ids)
            phrase_ids = set.intersection(*bigram_sets) if bigram_sets else set()
            if not phrase_ids:
                return []

        # Build TokenHit list across (stem × field). For phrase queries,
        # restrict to phrase_ids so BM25 is computed only over the
        # candidates that passed the bigram gate above.
        token_hits: list[TokenHit] = []
        for stem in stems:
            for field_long in target_fields:
                field_short = _LONG_TO_SHORT[field_long]
                bt = blind_token(owner_sse_key, field_short, stem)
                entries = self._load_posting(principal_id, owner_sse_key, bt)
                if not entries:
                    continue
                authorized_entries = [
                    e for e in entries
                    if e.get("collection_id") in authorized_collections
                    and (phrase_ids is None or e.get("artifact_id") in phrase_ids)
                ]
                if not authorized_entries:
                    continue
                token_hits.append(
                    TokenHit(
                        blind_token=bt,
                        field=field_long,
                        entries=authorized_entries,
                    )
                )

        if not token_hits:
            return []

        scores = score_query(
            token_hits, owner_stats,
            field_boosts=self._field_boosts,
            k1=self._k1, b=self._b,
        )

        return [
            SseHit(
                artifact_id=art_id,
                collection_id=col_id,
                principal_id=principal_id,
                score=score,
            )
            for (art_id, col_id), score in scores.items()
        ]

    # ------------------------------------------------------------------
    # Cache-aware loaders
    # ------------------------------------------------------------------

    def _load_posting(
        self, principal_id: str, owner_sse_key: bytes, blind_token: str,
    ) -> list[dict]:
        """Return decrypted posting entries (cached). Returns [] for misses
        and for tampered blobs — one bad posting list must not DoS the
        whole query."""
        cached = self._posting_cache.get(principal_id, blind_token)
        if cached is not None:
            return cached
        blob = self._postings.get_posting(principal_id, blind_token)
        if blob is None:
            return []
        try:
            key = posting_mod.derive_posting_key(owner_sse_key, blind_token)
            entries = posting_mod.unpack_posting(blob, key)
        except posting_mod.PostingError as exc:
            logger.warning(
                "SSE: dropping unreadable posting list owner=%s token=%s reason=%s",
                principal_id, blind_token[:8], exc,
            )
            return []
        self._posting_cache.put(principal_id, blind_token, entries)
        return entries

    def _load_stats(
        self, principal_id: str, owner_sse_key: bytes,
    ) -> Optional[Stats]:
        """Return decrypted stats (cached). Returns ``None`` if the owner
        has no stats yet (first-commit not run) or if the blob is
        unreadable — in either case, BM25 has no information for this
        owner and contributions skip silently."""
        cached = self._stats_cache.get(principal_id)
        if cached is not None:
            return cached
        blob = self._stats.get(principal_id)
        if blob is None:
            return None
        try:
            key = stats_mod.derive_stats_key(owner_sse_key)
            owner_stats = stats_mod.unpack_stats(blob, key)
        except posting_mod.PostingError as exc:
            logger.warning(
                "SSE: dropping unreadable stats blob owner=%s reason=%s",
                principal_id, exc,
            )
            return None
        self._stats_cache.put(principal_id, owner_stats)
        return owner_stats

    # ------------------------------------------------------------------
    # Field resolution
    # ------------------------------------------------------------------

    def _resolve_fields(
        self, requested: Optional[Iterable[str]],
    ) -> list[str]:
        """Decide which long-form fields to search.

        - If ``requested`` is None → all four default fields.
        - Otherwise → the requested fields, filtered to known names.

        In both cases, fields with a zero/negative boost in
        :attr:`_field_boosts` are dropped (boost=0 means "don't use").
        Fields with no boost configured default to
        :data:`DEFAULT_FIELD_BOOST` (1.0) and are kept.
        """
        if requested is None:
            candidates: list[str] = list(_DEFAULT_FIELDS)
        else:
            candidates = [f for f in requested if f in _LONG_TO_SHORT]
        out: list[str] = []
        for f in candidates:
            boost = self._field_boosts.get(f, DEFAULT_FIELD_BOOST)
            if boost > 0:
                out.append(f)
        return out


__all__ = ["SseHit", "SseQueryEngine"]
