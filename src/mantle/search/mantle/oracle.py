"""OracleService — in-process key custodian for MANTLE encrypted search.

Step 2.2a implementation. Holds per-principal 256-bit master keys in memory,
loaded lazily from Fernet-wrapped storage on first access. Derives per-cell
AES-256-GCM keys via HKDF on demand — cell keys are never persisted.

The **principal** is the collection's immutable origin root (see
``search.mantle.principal``), NOT an "owner" / ``created_by``. Agience has no
owners — access is by grant — so the master-key root is the stable creation-lineage
root, which the index and query paths resolve identically (same key both ends).

Key derivation hierarchy:

    Principal master key (256 bits, Fernet-wrapped at rest)
      └─ HKDF-Extract+Expand(IKM=master, salt=fixed,
                             info=collection_id ‖ 0x00 ‖ cluster_id, len=32)
      → cell key (256-bit AES-GCM)

One cell per ``(principal_id, collection_id, cluster_id)`` where ``cluster_id`` is
the routing anchor (canonical plan §5.1: the AnchorSet IS the partition). There
is one path — every cell is anchor-routed; there is no flat / unpartitioned key.

Determinism: re-derivation always produces the same cell key for the same
(master_key, collection_id, cluster_id) tuple, which is essential for query-path
decryption.

See `.dev/features/mantle-mvp.md` § Layer 2a.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from typing import Protocol

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Crypto parameters
# ---------------------------------------------------------------------------

_MASTER_KEY_BYTES = 32          # 256-bit master keys
_CELL_KEY_BYTES = 32            # 256-bit AES-GCM cell keys
_SSE_KEY_BYTES = 32             # 256-bit per-principal SSE key (MANTLE-SSE)

# Fixed HKDF salt — versioned so a future v2 derivation scheme can coexist
# with v1-encrypted cells during a migration. Cell keys derived under
# different salts are independent.
_HKDF_SALT_V1 = b"agience-mantle-cell-key-v1"

# HKDF info string for the per-principal SSE key (MANTLE-SSE encrypted lexical).
# Distinct from cell-key derivation so the two key trees stay
# cryptographically independent — same master, different info, different key.
_HKDF_SSE_INFO = b"sse"


# ---------------------------------------------------------------------------
# Master key storage
# ---------------------------------------------------------------------------

class MasterKeyStore(Protocol):
    """Persistence boundary for principal master keys.

    The OracleService is agnostic to where keys live — Arango, Postgres,
    KMS, or a Shamir share quorum. Each backend implements ``get`` and ``put``.
    """

    def get(self, principal_id: str) -> bytes | None:
        """Return the unwrapped 256-bit master key for ``principal_id``, or None."""

    def put(self, principal_id: str, master_key: bytes) -> None:
        """Persist the master key for ``principal_id``. Implementations are
        responsible for at-rest encryption (Fernet wrapping, KMS, etc.)."""


class FernetMasterKeyStore:
    """Default master key store: Fernet-wraps each key with the platform
    encryption key, persists the wrapped token in a backing dict (intended to
    be overridden by an Arango-backed implementation in production).

    The MVP single-node implementation lives in process — there's no separate
    oracle node. Keys are unwrapped on read and never paged out.
    """

    def __init__(self, fernet: Fernet, persist: Mapping[str, str] | None = None) -> None:
        self._fernet = fernet
        # Persistence is delegated to caller-provided dict-like; production
        # uses an Arango-backed implementation, tests use plain dicts.
        self._persist: dict[str, str] = dict(persist or {})

    def get(self, principal_id: str) -> bytes | None:
        token = self._persist.get(principal_id)
        if not token:
            return None
        try:
            return self._fernet.decrypt(token.encode())
        except Exception as exc:
            logger.error("Failed to unwrap master key for %s: %s", principal_id, exc)
            return None

    def put(self, principal_id: str, master_key: bytes) -> None:
        token = self._fernet.encrypt(master_key).decode()
        self._persist[principal_id] = token

    @property
    def storage(self) -> dict[str, str]:
        """Read-only view of the wrapped storage. Intended for tests / inspection."""
        return dict(self._persist)


# ---------------------------------------------------------------------------
# OracleService
# ---------------------------------------------------------------------------

class OracleService:
    """Single-node, in-process key custodian. MVP implementation."""

    def __init__(self, store: MasterKeyStore) -> None:
        self._store = store
        self._lock = threading.RLock()
        # Cache unwrapped master keys for the process lifetime. Trade-off:
        # crypto round-trip cost vs. RAM. 32 bytes per principal is cheap.
        self._cache: dict[str, bytes] = {}

    # ------------------------------------------------------------------
    # Master key lifecycle
    # ------------------------------------------------------------------

    def get_or_create_master_key(self, principal_id: str) -> bytes:
        """Return the principal's master key, generating + persisting on first call.

        Thread-safe: concurrent first-access calls won't generate duplicate
        keys for the same principal.
        """
        if not principal_id:
            raise ValueError("principal_id is required")

        # Fast path: already cached.
        cached = self._cache.get(principal_id)
        if cached is not None:
            return cached

        with self._lock:
            # Double-check after acquiring the lock.
            cached = self._cache.get(principal_id)
            if cached is not None:
                return cached

            existing = self._store.get(principal_id)
            if existing is not None:
                if len(existing) != _MASTER_KEY_BYTES:
                    raise RuntimeError(
                        f"Master key for {principal_id} is {len(existing)} bytes, "
                        f"expected {_MASTER_KEY_BYTES}"
                    )
                self._cache[principal_id] = existing
                return existing

            # First use by this principal — generate.
            master_key = os.urandom(_MASTER_KEY_BYTES)
            self._store.put(principal_id, master_key)
            self._cache[principal_id] = master_key
            logger.info("Generated new MANTLE master key for principal=%s", principal_id)
            return master_key

    # ------------------------------------------------------------------
    # Cell key derivation
    # ------------------------------------------------------------------

    def derive_cell_key(
        self, principal_id: str, collection_id: str, cluster_id: str
    ) -> bytes:
        """HKDF(master_key, info=collection_id ‖ 0x00 ‖ cluster_id) → 256-bit AES key.

        ``cluster_id`` is the routing anchor of the cell (canonical plan §5.1:
        the AnchorSet IS the partition; one cell per ``(principal, collection,
        anchor)``) and is required — routing has no flat fallback, so there is no
        anchor-less key. Deterministic; cell keys are never persisted — callers
        re-derive on demand.
        """
        if not principal_id or not collection_id:
            raise ValueError("principal_id and collection_id are required")

        master_key = self.get_or_create_master_key(principal_id)
        return self._derive(master_key, collection_id, cluster_id)

    # ------------------------------------------------------------------
    # SSE key derivation (MANTLE-SSE encrypted lexical, Step 2.6)
    # ------------------------------------------------------------------

    def derive_sse_key(self, principal_id: str) -> bytes:
        """HKDF(master_key, info='sse') → 256-bit principal SSE key.

        The SSE key is derived per-principal (not per-collection) because SSE
        posting lists span a principal's entire corpus. Per-blind-token
        encryption keys are subsequently derived from the SSE key inside
        the posting list manager (:mod:`mantle.search.mantle.sse.posting`).

        Deterministic — re-derivation yields the same key.
        """
        if not principal_id:
            raise ValueError("principal_id is required")

        master_key = self.get_or_create_master_key(principal_id)
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=_SSE_KEY_BYTES,
            salt=_HKDF_SALT_V1,
            info=_HKDF_SSE_INFO,
        )
        return hkdf.derive(master_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive(master_key: bytes, collection_id: str, cluster_id: str) -> bytes:
        """Run the HKDF-SHA256 derivation for one cell.

        Info = ``collection_id ‖ 0x00 ‖ cluster_id`` — one formula, binding the
        key to exactly one ``(master_key, collection_id, cluster_id)`` tuple.
        ``cluster_id`` is always a real routing anchor; there is no anchor-less
        key.
        """
        info = collection_id.encode("utf-8") + b"\x00" + cluster_id.encode("utf-8")
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=_CELL_KEY_BYTES,
            salt=_HKDF_SALT_V1,
            info=info,
        )
        return hkdf.derive(master_key)

    # ------------------------------------------------------------------
    # Cache management (mainly for tests + admin reload)
    # ------------------------------------------------------------------

    def evict(self, principal_id: str | None = None) -> None:
        """Drop cached master keys. Pass ``principal_id`` to evict one principal;
        omit to clear the whole cache."""
        with self._lock:
            if principal_id is None:
                self._cache.clear()
            else:
                self._cache.pop(principal_id, None)
