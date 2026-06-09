"""MANTLE-SSE — encrypted lexical search (Step 2.6 scaffolding).

Per `.dev/features/mantle-sse-lexical-index.md`. Replaces OpenSearch BM25 with
blind-token posting lists encrypted in S3. Once 2.6 lands fully, the
`search` (OpenSearch) container can be retired entirely — completing the
four-container reduction.

Design summary:

- **Blind tokens**: deterministic HMAC-SHA256 over (owner_sse_key, field+term)
  produces opaque tokens. The S3 backing store sees only hex strings — never
  plaintext terms.
- **Posting lists**: per-blind-token JSON (entries: artifact_id, collection_id,
  field, tf, dl, positions), AES-256-GCM encrypted with HKDF-derived
  per-token keys.
- **Corpus stats**: per-owner aggregates (doc_count, avg_dl, df) encrypted
  with the owner's SSE key. Updated incrementally on commit.
- **BM25**: standard Okapi BM25 with field boosting, computed in-process
  after decrypting the relevant posting lists.
- **Authorization**: same light-cone BFS as the MANTLE vector layer. Both
  index paths share the authorized scope.

Layered atop the existing MANTLE vector infrastructure:

- :class:`OracleService` (existing) — extended with an ``sse`` derivation
  context for owner SSE keys.
- :class:`LightConeResolver` (existing) — reused unchanged.
- New SSE modules below — tokenizer, blind tokens, posting list manager,
  BM25 scorer, corpus stats, indexer, query engine.

After Step 2.6.9 (2026-05-09) the ``MANTLE_SSE_ENABLED`` flag is gone —
SSE is the canonical lexical backend. Phasing reference (historical):

- **2.6.0** — Package scaffolding + config flag (this commit).
- **2.6.1** — Tokenizer (English analysis: lowercase → possessive →
  stop words → Porter stemmer).
- **2.6.2** — Blind token generator (HMAC + field prefix + prefix tokens
  for title/tags).
- **2.6.3** — Posting list manager (S3 CRUD; HKDF + AES-256-GCM per
  blind token; manifest tracking per artifact).
- **2.6.4** — Corpus stats manager (per-owner aggregates).
- **2.6.5** — BM25 scorer (in-process, field-boosted via existing
  ``mantle/search/weights/*.json`` presets).
- **2.6.6** — Indexer + commit-path hook (parallel to ``MantleIndexer``).
- **2.6.7** — Query engine (constant-width batch lookup, BM25 scoring).
- **2.6.8** — Unified accessor (RRF fusion of MANTLE vector + SSE lexical;
  no OpenSearch arm).
- **2.6.9** — Migration: re-index existing artifacts via SSE; retire
  OpenSearch; drop ``search`` service from compose. Done 2026-05-09.
"""

from __future__ import annotations

from .blind_tokens import (
    FIELD_CONTENT,
    FIELD_DESCRIPTION,
    FIELD_TAGS,
    FIELD_TITLE,
    PREFIX_FIELDS,
    PREFIX_LENGTHS,
    VALID_FIELDS,
    blind_token,
    blind_tokens_for_terms,
    prefix_blind_token,
    prefix_blind_tokens,
)
from .posting import (
    InMemoryPostingStore,
    PostingError,
    PostingMalformed,
    PostingStore,
    PostingTampered,
    artifact_ids_in_entries,
    decrypt_blob,
    derive_manifest_key,
    derive_posting_key,
    deserialize_entries,
    deserialize_manifest,
    encrypt_blob,
    entry_count,
    pack_manifest,
    pack_posting,
    remove_artifact_collection_entries,
    remove_artifact_entries,
    serialize_entries,
    serialize_manifest,
    unpack_manifest,
    unpack_posting,
    upsert_entry,
)
from .indexer import SseIndexer
from .query import SseHit, SseQueryEngine
from .router_accessor import MantleSseSearchAccessor
from .s3_stores import S3PostingStore, S3StatsStore
from .unified import MantleUnifiedAccessor, HitSource, UnifiedHit
from .scorer import (
    DEFAULT_B,
    DEFAULT_FIELD_BOOST,
    DEFAULT_K1,
    TokenHit,
    bm25_term_score,
    idf,
    normalized_tf,
    score_query,
)
from .stats import (
    InMemoryStatsStore,
    Stats,
    StatsStore,
    add_document,
    derive_stats_key,
    deserialize_stats,
    empty_stats,
    pack_stats,
    remove_document,
    serialize_stats,
    unpack_stats,
)
from .tokenizer import (
    STOP_WORDS,
    is_stop_word,
    porter_stem,
    split_words,
    strip_possessive,
    tokenize,
)

__all__ = [
    # Tokenizer
    "STOP_WORDS",
    "is_stop_word",
    "porter_stem",
    "split_words",
    "strip_possessive",
    "tokenize",
    # Blind tokens
    "FIELD_TITLE",
    "FIELD_DESCRIPTION",
    "FIELD_TAGS",
    "FIELD_CONTENT",
    "VALID_FIELDS",
    "PREFIX_FIELDS",
    "PREFIX_LENGTHS",
    "blind_token",
    "blind_tokens_for_terms",
    "prefix_blind_token",
    "prefix_blind_tokens",
    # Posting list manager (Step 2.6.3)
    "PostingError",
    "PostingMalformed",
    "PostingTampered",
    "derive_posting_key",
    "derive_manifest_key",
    "encrypt_blob",
    "decrypt_blob",
    "serialize_entries",
    "deserialize_entries",
    "pack_posting",
    "unpack_posting",
    "serialize_manifest",
    "deserialize_manifest",
    "pack_manifest",
    "unpack_manifest",
    "upsert_entry",
    "remove_artifact_entries",
    "remove_artifact_collection_entries",
    "entry_count",
    "artifact_ids_in_entries",
    "PostingStore",
    "InMemoryPostingStore",
    # Corpus stats (Step 2.6.4)
    "Stats",
    "derive_stats_key",
    "serialize_stats",
    "deserialize_stats",
    "pack_stats",
    "unpack_stats",
    "empty_stats",
    "add_document",
    "remove_document",
    "StatsStore",
    "InMemoryStatsStore",
    # BM25 scorer (Step 2.6.5)
    "DEFAULT_K1",
    "DEFAULT_B",
    "DEFAULT_FIELD_BOOST",
    "TokenHit",
    "idf",
    "normalized_tf",
    "bm25_term_score",
    "score_query",
    # Commit-path indexer (Step 2.6.6)
    "SseIndexer",
    # Query engine (Step 2.6.7)
    "SseHit",
    "SseQueryEngine",
    # Unified accessor (Step 2.6.8)
    "MantleUnifiedAccessor",
    "HitSource",
    "UnifiedHit",
    # S3-backed production stores (Step 2.6.9)
    "S3PostingStore",
    "S3StatsStore",
    # Router-shape adapter (Step 2.6.9)
    "MantleSseSearchAccessor",
]
