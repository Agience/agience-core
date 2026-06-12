"""Per-owner corpus statistics for MANTLE-SSE BM25 (Step 2.6.4).

BM25 needs three numbers per query:

- ``N`` — total documents in the corpus → :attr:`Stats.doc_count`
- ``avg_dl[field]`` — average document length (in tokens) per field
- ``df[blind_token]`` — document frequency per term (per blind token)

Stats are scoped per-owner and updated incrementally on commit. Wire
format (encrypted, AES-256-GCM under a stats key derived from the
owner's SSE key) tracks running *totals* rather than the spec's
``avg_dl`` floats — exact integer arithmetic avoids float-drift after
many updates. ``avg_dl`` is computed on read.

Wire schema (canonical JSON, sorted keys, no whitespace)::

    {
      "doc_count":         4200,
      "field_doc_count":   {"title": 4200, "description": 4180, ...},
      "field_total_dl":    {"title": 26040, "description": 103664, ...},
      "df":                {"<blind_token>": 17, ...}
    }

The encryption key for the stats blob is derived from the owner's SSE
key with HKDF info ``"stats"``, mirroring how :mod:`posting` derives
per-token / per-manifest keys. Stats are encrypted under their own key
(rather than the owner's SSE key directly) so the SSE key remains a
namespace root that never sees AES-GCM operations itself.

See ``internal design notes`` § Corpus Stats and
§ BM25 Scoring.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Iterable, Optional, Protocol

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .posting import (
    PostingMalformed,
    decrypt_blob,
    encrypt_blob,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Crypto parameters
# ---------------------------------------------------------------------------

_KEY_BYTES = 32
_OWNER_SSE_KEY_BYTES = 32

# Reuses the posting-tree HKDF salt — we're in the same v1 SSE namespace.
# Distinct ``info`` keeps stats keys independent from per-token / per-manifest
# keys.
_HKDF_SALT_V1 = b"agience-mantle-sse-posting-v1"
_INFO_STATS = b"stats"


def _validate_owner_sse_key(owner_sse_key: bytes) -> None:
    if not isinstance(owner_sse_key, (bytes, bytearray)):
        raise TypeError(
            f"owner_sse_key must be bytes, got {type(owner_sse_key).__name__}"
        )
    if len(owner_sse_key) != _OWNER_SSE_KEY_BYTES:
        raise ValueError(
            f"owner_sse_key must be {_OWNER_SSE_KEY_BYTES} bytes, "
            f"got {len(owner_sse_key)}"
        )


def derive_stats_key(owner_sse_key: bytes) -> bytes:
    """Derive the AES-256-GCM key for the owner's stats blob.

    ``key = HKDF-Expand(owner_sse_key, info="stats")``. Deterministic.
    """
    _validate_owner_sse_key(owner_sse_key)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_BYTES,
        salt=_HKDF_SALT_V1,
        info=_INFO_STATS,
    ).derive(bytes(owner_sse_key))


# ---------------------------------------------------------------------------
# Stats dataclass
# ---------------------------------------------------------------------------


@dataclass
class Stats:
    """Per-owner BM25 corpus aggregates.

    Stored: integer running totals (collision- and drift-free).
    Derived: ``avg_dl[field]`` via :meth:`average_dl`.
    """

    doc_count: int = 0
    field_doc_count: dict[str, int] = field(default_factory=dict)
    field_total_dl: dict[str, int] = field(default_factory=dict)
    df: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Derived views (BM25 inputs)
    # ------------------------------------------------------------------

    def average_dl(self, field_name: str) -> float:
        """Return ``avg_dl[field]`` — mean document length over docs that
        have any tokens in ``field_name``. Returns 0.0 for absent fields."""
        n = self.field_doc_count.get(field_name, 0)
        if n <= 0:
            return 0.0
        return self.field_total_dl.get(field_name, 0) / n

    def average_dl_all(self) -> dict[str, float]:
        """Return ``{field: avg_dl}`` for every tracked field."""
        return {f: self.average_dl(f) for f in self.field_doc_count}

    def df_for(self, blind_token: str) -> int:
        """Document frequency for one blind token. Returns 0 if absent."""
        return self.df.get(blind_token, 0)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_stats(stats: Stats) -> bytes:
    """Encode ``Stats`` as canonical JSON. Sorted keys, no whitespace."""
    payload = {
        "doc_count": int(stats.doc_count),
        "field_doc_count": {k: int(v) for k, v in stats.field_doc_count.items()},
        "field_total_dl": {k: int(v) for k, v in stats.field_total_dl.items()},
        "df": {k: int(v) for k, v in stats.df.items()},
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deserialize_stats(plaintext: bytes) -> Stats:
    """Decode canonical JSON back into a :class:`Stats` instance.

    Raises :class:`PostingMalformed` on JSON or schema errors. Reuses the
    posting module's malformed exception so callers have one error class
    per encryption tree.
    """
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PostingMalformed(
            f"stats plaintext is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise PostingMalformed(
            f"stats plaintext must decode to an object, "
            f"got {type(payload).__name__}"
        )
    try:
        doc_count = int(payload["doc_count"])
        field_doc_count = {
            str(k): int(v) for k, v in payload["field_doc_count"].items()
        }
        field_total_dl = {
            str(k): int(v) for k, v in payload["field_total_dl"].items()
        }
        df = {str(k): int(v) for k, v in payload["df"].items()}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise PostingMalformed(f"stats schema invalid: {exc}") from exc
    return Stats(
        doc_count=doc_count,
        field_doc_count=field_doc_count,
        field_total_dl=field_total_dl,
        df=df,
    )


def pack_stats(stats: Stats, key: bytes) -> bytes:
    """Serialize + encrypt in one call. Returns the at-rest blob."""
    return encrypt_blob(serialize_stats(stats), key)


def unpack_stats(blob: bytes, key: bytes) -> Stats:
    """Decrypt + deserialize. Inverse of :func:`pack_stats`."""
    return deserialize_stats(decrypt_blob(blob, key))


# ---------------------------------------------------------------------------
# Mutation helpers (incremental update on commit)
# ---------------------------------------------------------------------------


def empty_stats() -> Stats:
    """Return a freshly-zeroed :class:`Stats` instance."""
    return Stats()


def add_document(
    stats: Stats,
    *,
    field_dls: dict[str, int],
    blind_tokens: Iterable[str],
) -> Stats:
    """Apply a single-document insert to ``stats``. Mutates and returns it.

    ``field_dls`` is the per-field document length in tokens
    (``{"title": 6, "content": 482, ...}``). Fields with ``dl == 0`` (no
    tokens after analysis) are *not* counted against the field's doc count
    or total length — same approximation Lucene's BM25 makes.

    ``blind_tokens`` is the *deduplicated* set of blind tokens the document
    produced across all fields. Each unique token contributes 1 to ``df``.
    Callers must dedupe; passing the raw token sequence would over-count
    document frequency.
    """
    stats.doc_count += 1
    for field_name, dl in field_dls.items():
        if dl <= 0:
            continue
        stats.field_doc_count[field_name] = (
            stats.field_doc_count.get(field_name, 0) + 1
        )
        stats.field_total_dl[field_name] = (
            stats.field_total_dl.get(field_name, 0) + int(dl)
        )
    for tok in blind_tokens:
        if not tok:
            continue
        stats.df[tok] = stats.df.get(tok, 0) + 1
    return stats


def remove_document(
    stats: Stats,
    *,
    field_dls: dict[str, int],
    blind_tokens: Iterable[str],
) -> Stats:
    """Reverse :func:`add_document` for the same document. Mutates ``stats``.

    Counters are clamped at 0 — calling :func:`remove_document` with stale
    inputs (or a doc that was never added) won't drive any counter
    negative. Tokens whose ``df`` reaches 0 are dropped from the dict so
    the wire format stays compact.

    Returns ``stats`` for chaining.
    """
    stats.doc_count = max(0, stats.doc_count - 1)
    for field_name, dl in field_dls.items():
        if dl <= 0:
            continue
        if field_name in stats.field_doc_count:
            stats.field_doc_count[field_name] = max(
                0, stats.field_doc_count[field_name] - 1
            )
            if stats.field_doc_count[field_name] == 0:
                del stats.field_doc_count[field_name]
        if field_name in stats.field_total_dl:
            stats.field_total_dl[field_name] = max(
                0, stats.field_total_dl[field_name] - int(dl)
            )
            if stats.field_total_dl[field_name] == 0:
                del stats.field_total_dl[field_name]
    for tok in blind_tokens:
        if not tok or tok not in stats.df:
            continue
        stats.df[tok] -= 1
        if stats.df[tok] <= 0:
            del stats.df[tok]
    return stats


# ---------------------------------------------------------------------------
# Storage Protocol
# ---------------------------------------------------------------------------


class StatsStore(Protocol):
    """Encrypted per-owner stats blob storage.

    One stats blob per owner. The indexer reads-modify-writes the blob on
    every commit; the query engine reads it once per query (cached in
    process across queries via the MantleQueryEngine's stats cache, when
    that lands in 2.6.7).

    Production S3 layout: ``{tenant}/{principal_id}/sse/stats.enc``.
    """

    def get(self, principal_id: str) -> Optional[bytes]:
        """Return the encrypted stats blob, or None if no stats stored yet."""

    def put(self, principal_id: str, blob: bytes) -> None:
        """Persist (or overwrite) the stats blob."""

    def delete(self, principal_id: str) -> None:
        """Remove the stats blob. No-op if absent. Used by full-tenant
        teardown."""


class InMemoryStatsStore:
    """Thread-safe dict-backed StatsStore. Test default; not durable."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}
        self._lock = threading.RLock()

    def get(self, principal_id: str) -> Optional[bytes]:
        with self._lock:
            return self._blobs.get(principal_id)

    def put(self, principal_id: str, blob: bytes) -> None:
        with self._lock:
            self._blobs[principal_id] = blob

    def delete(self, principal_id: str) -> None:
        with self._lock:
            self._blobs.pop(principal_id, None)


__all__ = [
    "InMemoryStatsStore",
    "Stats",
    "StatsStore",
    "add_document",
    "derive_stats_key",
    "deserialize_stats",
    "empty_stats",
    "pack_stats",
    "remove_document",
    "serialize_stats",
    "unpack_stats",
]
