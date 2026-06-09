"""Encrypted posting-list manager for MANTLE-SSE (Step 2.6.3).

A *posting list* is the encrypted unit of lexical storage: one blob per
``(principal_id, blind_token)``. Each posting list holds the entries for every
artifact whose tokenized text — under the blind token's implicit
``(field, term)`` — produces that token. The S3 backing store sees only
opaque hex-named blobs; plaintext terms never leave the indexer / query
engine.

Wire format (binary, AES-256-GCM, mirrors ``cell.py``):

    posting_blob = nonce (12 bytes) ‖ ciphertext ‖ tag (16 bytes)

Cell plaintext is canonical JSON (sorted keys, no whitespace) of either:

- a posting list — ``{"entries": [<PostingEntry>, ...]}``
- an artifact manifest — ``{"tokens": [<blind_token>, ...]}``

Per-token / per-manifest keys are derived deterministically from the
owner's SSE key via HKDF with distinct ``info`` prefixes
(``"posting:<token>"`` vs ``"manifest:<artifact_id>"``) so the two key
trees stay independent.

This module knows nothing about S3, the indexer, or the query engine — by
design. The :class:`PostingStore` Protocol is the storage boundary; an
S3-backed implementation will live in ``mantle/search/mantle/wiring.py``
alongside the existing ``S3CellStore``.

See ``.dev/features/mantle-sse-lexical-index.md`` § Posting List Contents
and § Deletion / Revocation.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Iterable, List, Optional, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Crypto parameters
# ---------------------------------------------------------------------------

_NONCE_BYTES = 12          # AES-GCM standard 96-bit nonce
_KEY_BYTES = 32            # 256-bit AES-GCM key
_GCM_TAG_BYTES = 16
_OWNER_SSE_KEY_BYTES = 32  # matches OracleService.derive_sse_key

# HKDF salt — versioned so a future v2 key tree can coexist with v1-encrypted
# postings during a migration. Postings encrypted under different salts are
# independent.
_HKDF_SALT_V1 = b"agience-mantle-sse-posting-v1"

# Distinct info prefixes keep the posting-list and manifest key trees from
# colliding. Format: ``b"<prefix>:<id>"`` where id is ASCII (blind token hex
# or UUID). Both ids are fixed-length so length-prefixing isn't needed.
_INFO_PREFIX_POSTING = b"posting:"
_INFO_PREFIX_MANIFEST = b"manifest:"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PostingError(Exception):
    """Base class for posting-list crypto / format errors."""


class PostingTampered(PostingError):
    """Raised when a posting blob fails GCM authentication."""


class PostingMalformed(PostingError):
    """Raised when a posting blob is too short or contains invalid JSON."""


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

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


def _validate_aead_key(key: bytes) -> None:
    if len(key) != _KEY_BYTES:
        raise ValueError(f"AEAD key must be {_KEY_BYTES} bytes, got {len(key)}")


def _validate_blind_token(blind_token: str) -> None:
    if not blind_token:
        raise ValueError("blind_token is required")
    if len(blind_token) != 64:
        raise ValueError(
            f"blind_token must be 64 hex chars, got {len(blind_token)}"
        )
    # Cheap shape check — full hex validation is the indexer's concern.
    try:
        int(blind_token, 16)
    except ValueError as exc:
        raise ValueError(f"blind_token must be hex: {blind_token!r}") from exc


def _validate_artifact_id(artifact_id: str) -> None:
    if not artifact_id:
        raise ValueError("artifact_id is required")


# ---------------------------------------------------------------------------
# Per-posting-list / per-manifest key derivation
# ---------------------------------------------------------------------------

def derive_posting_key(owner_sse_key: bytes, blind_token: str) -> bytes:
    """Derive the AES-256-GCM key for one posting list.

    ``key = HKDF-Expand(owner_sse_key, info="posting:<blind_token>")``.

    Deterministic — re-derivation yields the same key. Per-blind-token
    independence means a key compromise in one posting list cannot decrypt
    another, even within the same owner.
    """
    _validate_owner_sse_key(owner_sse_key)
    _validate_blind_token(blind_token)
    return _hkdf(
        ikm=bytes(owner_sse_key),
        info=_INFO_PREFIX_POSTING + blind_token.encode("ascii"),
    )


def derive_manifest_key(owner_sse_key: bytes, artifact_id: str) -> bytes:
    """Derive the AES-256-GCM key for one artifact's blind-token manifest.

    ``key = HKDF-Expand(owner_sse_key, info="manifest:<artifact_id>")``.

    Manifests track which posting lists reference an artifact, so the
    deletion path can locate every posting list it must rewrite when the
    artifact is removed (per MANTLE-SSE spec § Deletion / Revocation).
    """
    _validate_owner_sse_key(owner_sse_key)
    _validate_artifact_id(artifact_id)
    return _hkdf(
        ikm=bytes(owner_sse_key),
        info=_INFO_PREFIX_MANIFEST + artifact_id.encode("ascii"),
    )


def _hkdf(*, ikm: bytes, info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_BYTES,
        salt=_HKDF_SALT_V1,
        info=info,
    ).derive(ikm)


# ---------------------------------------------------------------------------
# Encrypt / decrypt primitives (mirror cell.py)
# ---------------------------------------------------------------------------

def encrypt_blob(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt ``plaintext`` under a 256-bit AES-GCM key.

    Returns ``nonce ‖ ciphertext ‖ tag``. A fresh 96-bit nonce is drawn from
    ``os.urandom`` for every call — never reuse a (key, nonce) pair.
    """
    _validate_aead_key(key)
    aead = AESGCM(key)
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + aead.encrypt(nonce, plaintext, associated_data=None)


def decrypt_blob(blob: bytes, key: bytes) -> bytes:
    """Decrypt a blob produced by :func:`encrypt_blob`.

    Raises :class:`PostingTampered` on GCM tag failure (wrong key or
    modified ciphertext). Raises :class:`PostingMalformed` if the blob
    is shorter than the nonce + tag overhead.
    """
    _validate_aead_key(key)
    if len(blob) < _NONCE_BYTES + _GCM_TAG_BYTES:
        raise PostingMalformed(f"posting blob too short ({len(blob)} bytes)")

    nonce = blob[:_NONCE_BYTES]
    ciphertext_and_tag = blob[_NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext_and_tag, associated_data=None)
    except InvalidTag as exc:
        raise PostingTampered(
            "posting GCM tag failed — wrong key or modified ciphertext"
        ) from exc


# ---------------------------------------------------------------------------
# Posting-list serialization
# ---------------------------------------------------------------------------

def serialize_entries(entries: List[dict]) -> bytes:
    """Encode a list of posting entries as canonical JSON bytes.

    Wraps the list in ``{"entries": [...]}`` so the outer envelope stays
    extensible (future fields like ``"version"`` or ``"compressed"`` can be
    added without rewriting every existing blob).
    """
    payload = {"entries": entries}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deserialize_entries(plaintext: bytes) -> List[dict]:
    """Decode the canonical JSON form produced by :func:`serialize_entries`.

    Raises :class:`PostingMalformed` if the plaintext isn't valid JSON, the
    outer envelope isn't an object, or ``"entries"`` isn't a list.
    """
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PostingMalformed(
            f"posting plaintext is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise PostingMalformed(
            f"posting plaintext must decode to an object, "
            f"got {type(payload).__name__}"
        )
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise PostingMalformed(
            f"posting payload missing list 'entries', got {type(entries).__name__}"
        )
    return entries


def pack_posting(entries: List[dict], key: bytes) -> bytes:
    """Serialize + encrypt in one call. Returns the at-rest blob."""
    return encrypt_blob(serialize_entries(entries), key)


def unpack_posting(blob: bytes, key: bytes) -> List[dict]:
    """Decrypt + deserialize. Inverse of :func:`pack_posting`."""
    return deserialize_entries(decrypt_blob(blob, key))


# ---------------------------------------------------------------------------
# Manifest serialization (per-artifact tracker — tokens + field_dls)
# ---------------------------------------------------------------------------

def serialize_manifest(
    blind_tokens: Iterable[str],
    *,
    field_dls: Optional[dict[str, int]] = None,
) -> bytes:
    """Encode an artifact's manifest as canonical JSON.

    Wire shape::

        {"tokens": ["<bt1>", ...], "field_dls": {"title": 6, ...}}

    Tokens are de-duplicated and sorted so the on-disk representation is
    stable — useful for cache fingerprinting and for diffing manifests
    during incremental updates. ``field_dls`` carries the per-field
    document length (token count) the artifact was indexed at; the
    indexer needs it on re-index to subtract the old document's
    contribution from corpus stats before adding the new one.

    The doc spec ("§ Deletion / Revocation") describes the manifest as a
    flat list of blind tokens. We enrich it here so a single read
    suffices for both revocation (read tokens, scan posting lists) and
    re-index (read tokens + field_dls, undo old stats contribution).
    """
    deduped = sorted({str(t) for t in blind_tokens if t})
    dls = {str(k): int(v) for k, v in (field_dls or {}).items() if v}
    payload = {"tokens": deduped, "field_dls": dls}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deserialize_manifest(plaintext: bytes) -> tuple[List[str], dict[str, int]]:
    """Decode a manifest produced by :func:`serialize_manifest`.

    Returns ``(tokens, field_dls)`` where tokens is a sorted list of
    unique blind tokens and field_dls is the per-field document length
    dict (may be empty for legacy manifests written before the field was
    added). Raises :class:`PostingMalformed` if the JSON shape is wrong.
    """
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PostingMalformed(
            f"manifest plaintext is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise PostingMalformed(
            f"manifest plaintext must decode to an object, "
            f"got {type(payload).__name__}"
        )
    tokens_raw = payload.get("tokens")
    if not isinstance(tokens_raw, list):
        raise PostingMalformed(
            f"manifest payload missing list 'tokens', got {type(tokens_raw).__name__}"
        )
    tokens = [str(t) for t in tokens_raw]
    dls_raw = payload.get("field_dls", {})
    if not isinstance(dls_raw, dict):
        raise PostingMalformed(
            f"manifest payload 'field_dls' must be an object, "
            f"got {type(dls_raw).__name__}"
        )
    try:
        field_dls = {str(k): int(v) for k, v in dls_raw.items()}
    except (TypeError, ValueError) as exc:
        raise PostingMalformed(
            f"manifest 'field_dls' contains non-integer values: {exc}"
        ) from exc
    return tokens, field_dls


def pack_manifest(
    blind_tokens: Iterable[str],
    key: bytes,
    *,
    field_dls: Optional[dict[str, int]] = None,
) -> bytes:
    """Serialize + encrypt a manifest in one call."""
    return encrypt_blob(serialize_manifest(blind_tokens, field_dls=field_dls), key)


def unpack_manifest(blob: bytes, key: bytes) -> tuple[List[str], dict[str, int]]:
    """Decrypt + deserialize a manifest. Inverse of :func:`pack_manifest`.

    Returns ``(tokens, field_dls)``.
    """
    return deserialize_manifest(decrypt_blob(blob, key))


# ---------------------------------------------------------------------------
# Mutation helpers (read-modify-write pattern)
# ---------------------------------------------------------------------------

def upsert_entry(entries: List[dict], record: dict) -> List[dict]:
    """Insert or replace a posting entry by ``(artifact_id, collection_id)``.

    The unique key is the ``(artifact_id, collection_id)`` pair: the field
    is implicit in the posting list's blind token (one list per
    ``(field, term)``), and the same artifact in the same collection
    contributes one entry per posting list. Re-indexing the same artifact
    overwrites in place.

    Returns the same list reference for chaining.
    """
    artifact_id = record.get("artifact_id")
    collection_id = record.get("collection_id")
    if not artifact_id or not collection_id:
        raise ValueError(
            "posting entry must carry non-empty artifact_id and collection_id"
        )
    for i, existing in enumerate(entries):
        if (
            existing.get("artifact_id") == artifact_id
            and existing.get("collection_id") == collection_id
        ):
            entries[i] = record
            return entries
    entries.append(record)
    return entries


def remove_artifact_entries(entries: List[dict], artifact_id: str) -> List[dict]:
    """Strip every entry for ``artifact_id`` (across all its collections).

    Returns a *new* list (does not mutate the input). Used by the deletion
    path when an artifact is fully revoked.
    """
    return [e for e in entries if e.get("artifact_id") != artifact_id]


def remove_artifact_collection_entries(
    entries: List[dict], artifact_id: str, collection_id: str,
) -> List[dict]:
    """Strip entries for one ``(artifact_id, collection_id)`` pair only.

    Used by partial revocation: an artifact is removed from one collection
    but remains in others. Returns a new list.
    """
    return [
        e for e in entries
        if not (
            e.get("artifact_id") == artifact_id
            and e.get("collection_id") == collection_id
        )
    ]


def entry_count(entries: List[dict]) -> int:
    """Total entries — useful for empty-posting-list detection."""
    return len(entries)


def artifact_ids_in_entries(entries: List[dict]) -> set[str]:
    """Distinct artifact IDs present in a posting list."""
    return {e["artifact_id"] for e in entries if "artifact_id" in e}


# ---------------------------------------------------------------------------
# Storage Protocol
# ---------------------------------------------------------------------------

class PostingStore(Protocol):
    """Encrypted posting-list + manifest storage.

    The indexer writes both posting lists and per-artifact manifests; the
    query engine reads only posting lists; the deletion path reads manifests
    to find every posting list referencing the artifact, then rewrites each.

    Production S3 layout:
      ``{tenant}/{principal_id}/sse/posting/{blind_token}.enc``
      ``{tenant}/{principal_id}/sse/manifests/{artifact_id}.enc``
    """

    # Posting-list operations
    def get_posting(self, principal_id: str, blind_token: str) -> Optional[bytes]:
        """Return the encrypted posting blob, or None."""

    def put_posting(self, principal_id: str, blind_token: str, blob: bytes) -> None:
        """Persist (or overwrite) the posting blob."""

    def delete_posting(self, principal_id: str, blind_token: str) -> None:
        """Remove the posting list. No-op if absent."""

    def list_tokens_for_owner(self, principal_id: str) -> List[str]:
        """Return every blind token with a stored posting list under
        ``principal_id``. Used by bulk re-key / migration paths."""

    # Manifest operations
    def get_manifest(self, principal_id: str, artifact_id: str) -> Optional[bytes]:
        """Return the encrypted manifest blob, or None."""

    def put_manifest(self, principal_id: str, artifact_id: str, blob: bytes) -> None:
        """Persist (or overwrite) the manifest blob."""

    def delete_manifest(self, principal_id: str, artifact_id: str) -> None:
        """Remove the manifest. No-op if absent."""


class InMemoryPostingStore:
    """Thread-safe dict-backed PostingStore. Test default; not durable."""

    def __init__(self) -> None:
        self._postings: dict[tuple[str, str], bytes] = {}
        self._manifests: dict[tuple[str, str], bytes] = {}
        self._lock = threading.RLock()

    # Posting-list operations
    def get_posting(self, principal_id: str, blind_token: str) -> Optional[bytes]:
        with self._lock:
            return self._postings.get((principal_id, blind_token))

    def put_posting(self, principal_id: str, blind_token: str, blob: bytes) -> None:
        with self._lock:
            self._postings[(principal_id, blind_token)] = blob

    def delete_posting(self, principal_id: str, blind_token: str) -> None:
        with self._lock:
            self._postings.pop((principal_id, blind_token), None)

    def list_tokens_for_owner(self, principal_id: str) -> List[str]:
        with self._lock:
            return [tok for (oid, tok) in self._postings if oid == principal_id]

    # Manifest operations
    def get_manifest(self, principal_id: str, artifact_id: str) -> Optional[bytes]:
        with self._lock:
            return self._manifests.get((principal_id, artifact_id))

    def put_manifest(self, principal_id: str, artifact_id: str, blob: bytes) -> None:
        with self._lock:
            self._manifests[(principal_id, artifact_id)] = blob

    def delete_manifest(self, principal_id: str, artifact_id: str) -> None:
        with self._lock:
            self._manifests.pop((principal_id, artifact_id), None)


__all__ = [
    # Errors
    "PostingError",
    "PostingMalformed",
    "PostingTampered",
    # Key derivation
    "derive_manifest_key",
    "derive_posting_key",
    # Crypto primitives
    "decrypt_blob",
    "encrypt_blob",
    # Posting-list (de)serialization
    "deserialize_entries",
    "pack_posting",
    "serialize_entries",
    "unpack_posting",
    # Manifest (de)serialization
    "deserialize_manifest",
    "pack_manifest",
    "serialize_manifest",
    "unpack_manifest",
    # Mutation helpers
    "artifact_ids_in_entries",
    "entry_count",
    "remove_artifact_collection_entries",
    "remove_artifact_entries",
    "upsert_entry",
    # Storage
    "InMemoryPostingStore",
    "PostingStore",
]
