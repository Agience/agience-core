"""SseIndexer — commit-path posting list + manifest + stats updater (Step 2.6.6).

Mirrors :class:`mantle.search.mantle.indexer.MantleIndexer` for the SSE
lexical index. Composes:

- :class:`OracleService` — derives the owner SSE key
- :mod:`tokenizer` — analysis pipeline (lowercase → possessive → stop
  → Porter stem)
- :mod:`blind_tokens` — HMAC-based exact + prefix token generation
- :mod:`posting` — encrypted posting list + manifest CRUD
- :mod:`stats` — per-owner BM25 corpus aggregates
- :class:`PostingStore` + :class:`StatsStore` — abstract storage

The indexer never touches S3 directly. Production wires up an S3-backed
``PostingStore`` and ``StatsStore``; tests use the in-memory variants.

API:

- :meth:`index_artifact` — analyze + write posting lists + manifest +
  stats. Idempotent under re-index: an existing manifest's tokens are
  diffed against the new set, dropped tokens get the artifact's entry
  removed, kept/new tokens get an upsert; old corpus stats contribution
  is subtracted before adding the new one.
- :meth:`remove_artifact` — read the manifest, evict the artifact's
  entry from every posting list it appears in, decrement corpus stats,
  delete the manifest.

Field naming convention:

- The blind-token API uses single-char field codes (``t`` / ``d`` /
  ``g`` / ``c``).
- Posting entries, stats, and field_dls use the long-form field names
  (``"title"`` / ``"description"`` / ``"tags"`` / ``"content"``) — what
  field-boost presets and downstream callers expect.

The indexer maps between the two via :data:`_LONG_TO_SHORT`.

See ``.dev/features/mantle-sse-lexical-index.md`` § Indexing Flow.
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping, Optional

from .blind_tokens import (
    FIELD_CONTENT,
    FIELD_DESCRIPTION,
    FIELD_TAGS,
    FIELD_TITLE,
    PREFIX_FIELDS,
    PREFIX_LENGTHS,
    blind_token,
    prefix_blind_token,
)
from .posting import (
    PostingStore,
    PostingTampered,
    derive_manifest_key,
    derive_posting_key,
    pack_manifest,
    pack_posting,
    remove_artifact_collection_entries,
    unpack_manifest,
    unpack_posting,
    upsert_entry,
)
from . import stats as stats_mod
from .stats import StatsStore
from .tokenizer import bigrams as _stem_bigrams, tokenize
from ..oracle import OracleService

logger = logging.getLogger(__name__)


# Long-form (BM25 / field-boost-preset) → short-form (blind-token API).
_LONG_TO_SHORT = {
    "title": FIELD_TITLE,
    "description": FIELD_DESCRIPTION,
    "tags": FIELD_TAGS,
    "content": FIELD_CONTENT,
}

# Long-form names of fields eligible for prefix tokens.
_PREFIX_LONG_FIELDS = frozenset({
    long_name for long_name, short in _LONG_TO_SHORT.items()
    if short in PREFIX_FIELDS
})


# ---------------------------------------------------------------------------
# Per-field analysis
# ---------------------------------------------------------------------------


def _analyze_field(text: str) -> tuple[list[str], dict[str, list[int]]]:
    """Tokenize one field's text. Returns ``(tokens, term_positions)``.

    ``tokens`` is the analyzed token sequence (post-stem).
    ``term_positions`` maps each unique stemmed term to the *list* of
    positions (token indices) where it appears. ``tf`` is implied by
    ``len(positions[term])``.

    Empty / whitespace-only text returns empty containers.
    """
    if not text:
        return [], {}
    tokens = tokenize(text)
    positions: dict[str, list[int]] = {}
    for i, term in enumerate(tokens):
        positions.setdefault(term, []).append(i)
    return tokens, positions


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------


class SseIndexer:
    """Commit-path indexer for MANTLE-SSE encrypted lexical search."""

    def __init__(
        self,
        oracle: OracleService,
        posting_store: PostingStore,
        stats_store: StatsStore,
    ) -> None:
        self._oracle = oracle
        self._postings = posting_store
        self._stats = stats_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_artifact(
        self,
        principal_id: str,
        collection_id: str,
        artifact_id: str,
        fields: Mapping[str, str],
    ) -> int:
        """Index (or re-index) one artifact. Returns the number of distinct
        blind tokens written / updated.

        ``fields`` maps long-form field name to its raw text. Only fields
        in :data:`_LONG_TO_SHORT` are indexed; others are silently ignored
        (so callers can pass artifact context dicts without filtering).

        Re-index path: if a manifest already exists for the artifact, its
        prior token list and ``field_dls`` are read, the corpus stats are
        rolled back to that prior contribution, then the new index state
        is applied. Tokens that were in the prior set but not the new
        one have the artifact's entry stripped (and the posting list
        deleted if it goes empty).
        """
        if not principal_id:
            raise ValueError("principal_id is required")
        if not collection_id:
            raise ValueError("collection_id is required")
        if not artifact_id:
            raise ValueError("artifact_id is required")

        owner_sse_key = self._oracle.derive_sse_key(principal_id)

        # ---- 1. Analyze each field -----------------------------------
        new_field_dls: dict[str, int] = {}
        # token → posting-entry-shape data (per the spec's wire format)
        new_entries: dict[str, dict] = {}

        for field_long, text in fields.items():
            if field_long not in _LONG_TO_SHORT:
                continue
            tokens, term_positions = _analyze_field(text)
            dl = len(tokens)
            if dl == 0:
                continue
            new_field_dls[field_long] = dl
            field_short = _LONG_TO_SHORT[field_long]

            # Exact tokens: one per unique term.
            for term, positions in term_positions.items():
                tok = blind_token(owner_sse_key, field_short, term)
                new_entries[tok] = {
                    "artifact_id": artifact_id,
                    "collection_id": collection_id,
                    "field": field_long,
                    "tf": len(positions),
                    "dl": dl,
                    "positions": list(positions),
                }

            # Prefix tokens (title + tags only): aggregate tf + positions
            # across every term sharing each prefix length / prefix string.
            if field_long in _PREFIX_LONG_FIELDS:
                for n in PREFIX_LENGTHS:
                    aggregate: dict[str, list[int]] = {}
                    for term, positions in term_positions.items():
                        if len(term) < n:
                            continue
                        prefix = term[:n]
                        aggregate.setdefault(prefix, []).extend(positions)
                    for prefix, positions in aggregate.items():
                        positions_sorted = sorted(positions)
                        tok = prefix_blind_token(
                            owner_sse_key, field_short, prefix, n,
                        )
                        new_entries[tok] = {
                            "artifact_id": artifact_id,
                            "collection_id": collection_id,
                            "field": field_long,
                            "tf": len(positions_sorted),
                            "dl": dl,
                            "positions": positions_sorted,
                        }

            # Bigram tokens: adjacent stem pairs for phrase-query support.
            # Uses blind_token with a space-joined pair as the "term" key —
            # safe because individual stems contain only alphabetic
            # characters after the Porter pipeline (no spaces in stems).
            for bigram in _stem_bigrams(tokens):
                tok = blind_token(owner_sse_key, field_short, bigram)
                if tok not in new_entries:
                    new_entries[tok] = {
                        "artifact_id": artifact_id,
                        "collection_id": collection_id,
                        "field": field_long,
                        "tf": 1,
                        "dl": dl,
                        "positions": [],
                    }

        new_tokens = set(new_entries.keys())

        # ---- 2. Read existing manifest (re-index detection) ----------
        manifest_key = derive_manifest_key(owner_sse_key, artifact_id)
        old_tokens: set[str] = set()
        old_field_dls: dict[str, int] = {}
        manifest_blob = self._postings.get_manifest(principal_id, artifact_id)
        if manifest_blob is not None:
            old_tokens_list, old_field_dls = unpack_manifest(
                manifest_blob, manifest_key
            )
            old_tokens = set(old_tokens_list)

        # ---- 3. Diff: drop tokens that left, upsert tokens that stay/arrive
        dropped = old_tokens - new_tokens
        for tok in dropped:
            self._strip_entry(
                principal_id, owner_sse_key, tok, artifact_id, collection_id,
            )

        for tok, entry in new_entries.items():
            self._upsert_into_posting(
                principal_id, owner_sse_key, tok, entry,
            )

        # ---- 4. Update manifest --------------------------------------
        if new_tokens or new_field_dls:
            self._postings.put_manifest(
                principal_id, artifact_id,
                pack_manifest(new_tokens, manifest_key, field_dls=new_field_dls),
            )
        else:
            # Empty artifact (no analyzable fields) — drop any stale manifest.
            self._postings.delete_manifest(principal_id, artifact_id)

        # ---- 5. Update corpus stats (subtract old, add new) ----------
        self._update_stats(
            principal_id, owner_sse_key,
            is_reindex=manifest_blob is not None,
            old_field_dls=old_field_dls, old_tokens=old_tokens,
            new_field_dls=new_field_dls, new_tokens=new_tokens,
        )

        return len(new_tokens)

    def remove_artifact(self, principal_id: str, artifact_id: str) -> int:
        """Strip every reference to ``artifact_id`` from the SSE index.

        Reads the artifact's manifest to find every blind token referencing
        it, evicts the entry from each posting list (deleting the list
        entirely if it goes empty), decrements corpus stats, and removes
        the manifest itself.

        Returns the number of posting lists touched. Returns 0 if no
        manifest exists for this artifact (no-op — already removed or
        never indexed).
        """
        if not principal_id or not artifact_id:
            raise ValueError("principal_id and artifact_id are required")

        owner_sse_key = self._oracle.derive_sse_key(principal_id)
        manifest_key = derive_manifest_key(owner_sse_key, artifact_id)
        manifest_blob = self._postings.get_manifest(principal_id, artifact_id)
        if manifest_blob is None:
            return 0

        old_tokens, old_field_dls = unpack_manifest(manifest_blob, manifest_key)

        touched = 0
        for tok in old_tokens:
            if self._strip_artifact_from_posting(
                principal_id, owner_sse_key, tok, artifact_id,
            ):
                touched += 1

        # Drop the manifest itself.
        self._postings.delete_manifest(principal_id, artifact_id)

        # Roll back stats.
        self._apply_stats_delta(
            principal_id, owner_sse_key,
            add_dls=None, add_tokens=None,
            remove_dls=old_field_dls, remove_tokens=set(old_tokens),
        )

        return touched

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _upsert_into_posting(
        self,
        principal_id: str,
        owner_sse_key: bytes,
        blind_token: str,
        entry: dict,
    ) -> None:
        """Read-modify-write one posting list with a single entry upsert."""
        key = derive_posting_key(owner_sse_key, blind_token)
        blob = self._postings.get_posting(principal_id, blind_token)
        entries = unpack_posting(blob, key) if blob else []
        upsert_entry(entries, entry)
        self._postings.put_posting(
            principal_id, blind_token, pack_posting(entries, key),
        )

    def _strip_entry(
        self,
        principal_id: str,
        owner_sse_key: bytes,
        blind_token: str,
        artifact_id: str,
        collection_id: str,
    ) -> bool:
        """Strip one (artifact, collection) entry from a posting list.

        Drops the posting list entirely if it goes empty. Returns True if
        an entry was actually removed.
        """
        blob = self._postings.get_posting(principal_id, blind_token)
        if blob is None:
            return False
        key = derive_posting_key(owner_sse_key, blind_token)
        entries = unpack_posting(blob, key)
        before = len(entries)
        entries = remove_artifact_collection_entries(
            entries, artifact_id, collection_id,
        )
        if len(entries) == before:
            return False
        if entries:
            self._postings.put_posting(
                principal_id, blind_token, pack_posting(entries, key),
            )
        else:
            self._postings.delete_posting(principal_id, blind_token)
        return True

    def _strip_artifact_from_posting(
        self,
        principal_id: str,
        owner_sse_key: bytes,
        blind_token: str,
        artifact_id: str,
    ) -> bool:
        """Strip every entry for ``artifact_id`` from one posting list
        (across all collections it appears in). Used by the deletion path."""
        blob = self._postings.get_posting(principal_id, blind_token)
        if blob is None:
            return False
        key = derive_posting_key(owner_sse_key, blind_token)
        entries = unpack_posting(blob, key)
        before = len(entries)
        entries = [e for e in entries if e.get("artifact_id") != artifact_id]
        if len(entries) == before:
            return False
        if entries:
            self._postings.put_posting(
                principal_id, blind_token, pack_posting(entries, key),
            )
        else:
            self._postings.delete_posting(principal_id, blind_token)
        return True

    def _update_stats(
        self,
        principal_id: str,
        owner_sse_key: bytes,
        *,
        is_reindex: bool,
        old_field_dls: dict[str, int],
        old_tokens: Iterable[str],
        new_field_dls: dict[str, int],
        new_tokens: Iterable[str],
    ) -> None:
        """Re-index aware stats update.

        On a fresh index: only ``add_document`` is applied with the new
        contribution. On a re-index: the prior contribution is subtracted
        first (using ``old_field_dls`` + ``old_tokens`` from the previous
        manifest), then the new contribution is added.
        """
        self._apply_stats_delta(
            principal_id, owner_sse_key,
            add_dls=new_field_dls if (new_field_dls or new_tokens) else None,
            add_tokens=set(new_tokens) if new_tokens else None,
            remove_dls=old_field_dls if is_reindex else None,
            remove_tokens=set(old_tokens) if is_reindex else None,
        )

    def _apply_stats_delta(
        self,
        principal_id: str,
        owner_sse_key: bytes,
        *,
        add_dls: Optional[dict[str, int]],
        add_tokens: Optional[set[str]],
        remove_dls: Optional[dict[str, int]],
        remove_tokens: Optional[set[str]],
    ) -> None:
        """Apply an arbitrary remove-then-add delta to the owner's stats blob."""
        stats_key = stats_mod.derive_stats_key(owner_sse_key)
        existing = self._stats.get(principal_id)
        if existing is not None:
            try:
                current = stats_mod.unpack_stats(existing, stats_key)
            except PostingTampered:
                logger.warning(
                    "Stats blob for owner %s failed GCM tag — key rotation or data reset; starting fresh",
                    principal_id,
                )
                current = stats_mod.empty_stats()
        else:
            current = stats_mod.empty_stats()

        if remove_dls is not None or remove_tokens is not None:
            stats_mod.remove_document(
                current,
                field_dls=remove_dls or {},
                blind_tokens=remove_tokens or set(),
            )
        if add_dls is not None or add_tokens is not None:
            stats_mod.add_document(
                current,
                field_dls=add_dls or {},
                blind_tokens=add_tokens or set(),
            )

        self._stats.put(principal_id, stats_mod.pack_stats(current, stats_key))


__all__ = ["SseIndexer"]
