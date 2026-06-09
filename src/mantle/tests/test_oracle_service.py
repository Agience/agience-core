"""Unit tests for `search.mantle.OracleService` (Step 2.2a).

The OracleService manages per-owner master keys and derives per-cell AES-256-GCM
keys via HKDF. Tests cover:

- Master key generation (size, randomness, persistence round-trip)
- Idempotency (second call for the same owner returns the same key)
- Concurrent first-access doesn't generate duplicates
- HKDF determinism (same inputs → same key)
- HKDF independence (different inputs → different keys)
- Validation (rejects empty owner / collection)
- Cache eviction
- Integrity check on stored keys (wrong-length value rejected)

No FAISS, no S3 — pure crypto round-trips.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet

from search.mantle.oracle import (
    FernetMasterKeyStore,
    OracleService,
    _CELL_KEY_BYTES,
    _MASTER_KEY_BYTES,
)


@pytest.fixture
def fernet() -> Fernet:
    return Fernet(Fernet.generate_key())


@pytest.fixture
def store(fernet) -> FernetMasterKeyStore:
    return FernetMasterKeyStore(fernet)


@pytest.fixture
def oracle(store) -> OracleService:
    return OracleService(store)


# ---------------------------------------------------------------------------
# Master key lifecycle
# ---------------------------------------------------------------------------

class TestMasterKey:
    def test_generates_256_bit_key_on_first_call(self, oracle):
        key = oracle.get_or_create_master_key("owner-1")
        assert isinstance(key, bytes)
        assert len(key) == _MASTER_KEY_BYTES  # 32 bytes / 256 bits

    def test_second_call_returns_same_key(self, oracle):
        first = oracle.get_or_create_master_key("owner-1")
        second = oracle.get_or_create_master_key("owner-1")
        assert first == second

    def test_different_owners_get_different_keys(self, oracle):
        a = oracle.get_or_create_master_key("owner-a")
        b = oracle.get_or_create_master_key("owner-b")
        assert a != b

    def test_key_persists_across_oracle_instances(self, store):
        # Owner A creates a key via one oracle.
        oracle1 = OracleService(store)
        key1 = oracle1.get_or_create_master_key("owner-x")
        # A fresh oracle backed by the same store recovers the same key.
        oracle2 = OracleService(store)
        key2 = oracle2.get_or_create_master_key("owner-x")
        assert key1 == key2

    def test_keys_are_fernet_wrapped_at_rest(self, store):
        oracle = OracleService(store)
        oracle.get_or_create_master_key("owner-1")
        # Storage holds Fernet tokens, not raw bytes.
        wrapped = store.storage["owner-1"]
        assert isinstance(wrapped, str)
        assert wrapped.startswith("gAAAAAB")  # Fernet token prefix

    def test_empty_principal_id_rejected(self, oracle):
        with pytest.raises(ValueError, match="principal_id"):
            oracle.get_or_create_master_key("")

    def test_corrupted_storage_size_rejected(self, fernet):
        # Pre-populate the store with a wrong-size token.
        bad_store = FernetMasterKeyStore(fernet)
        bad_store.put("owner-1", b"too-short")  # only 9 bytes
        oracle = OracleService(bad_store)
        with pytest.raises(RuntimeError, match="bytes, expected"):
            oracle.get_or_create_master_key("owner-1")

    def test_concurrent_first_access_does_not_duplicate(self, store):
        """Two threads racing on first-access produce one key, not two."""
        oracle = OracleService(store)
        barrier = threading.Barrier(8)
        results: list[bytes] = []
        results_lock = threading.Lock()

        def worker():
            barrier.wait()
            key = oracle.get_or_create_master_key("owner-race")
            with results_lock:
                results.append(key)

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(lambda _: worker(), range(8)))

        assert len(results) == 8
        # All threads observed the same key.
        assert all(k == results[0] for k in results)
        # And the store has exactly one entry for the owner.
        assert list(store.storage.keys()) == ["owner-race"]


# ---------------------------------------------------------------------------
# Cell key derivation
# ---------------------------------------------------------------------------

class TestCellKeyDerivation:
    def test_derive_returns_256_bit_key(self, oracle):
        key = oracle.derive_cell_key("owner-1", "col-A", "anchor-1")
        assert isinstance(key, bytes)
        assert len(key) == _CELL_KEY_BYTES

    def test_derivation_is_deterministic(self, oracle):
        a = oracle.derive_cell_key("owner-1", "col-A", "anchor-1")
        b = oracle.derive_cell_key("owner-1", "col-A", "anchor-1")
        assert a == b

    def test_different_collections_produce_different_keys(self, oracle):
        a = oracle.derive_cell_key("owner-1", "col-A", "anchor-1")
        b = oracle.derive_cell_key("owner-1", "col-B", "anchor-1")
        assert a != b

    def test_different_clusters_produce_different_keys(self, oracle):
        a = oracle.derive_cell_key("owner-1", "col-A", "anchor-1")
        b = oracle.derive_cell_key("owner-1", "col-A", "anchor-2")
        assert a != b

    def test_different_owners_produce_different_keys(self, oracle):
        a = oracle.derive_cell_key("owner-1", "col-A", "anchor-1")
        b = oracle.derive_cell_key("owner-2", "col-A", "anchor-1")
        assert a != b

    def test_empty_inputs_rejected(self, oracle):
        with pytest.raises(ValueError):
            oracle.derive_cell_key("", "col-A", "anchor-1")
        with pytest.raises(ValueError):
            oracle.derive_cell_key("owner-1", "", "anchor-1")


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

class TestCache:
    def test_evict_specific_owner(self, oracle, store):
        oracle.get_or_create_master_key("owner-1")
        oracle.get_or_create_master_key("owner-2")
        oracle.evict("owner-1")
        # owner-1 is re-loaded from store on next access (still same key).
        reloaded = oracle.get_or_create_master_key("owner-1")
        wrapped = store.storage["owner-1"]
        unwrapped = store.get("owner-1")
        assert reloaded == unwrapped
        assert wrapped  # storage retained the wrapped token

    def test_evict_all(self, oracle):
        oracle.get_or_create_master_key("owner-1")
        oracle.get_or_create_master_key("owner-2")
        oracle.evict()
        # Both owners reload from store; they keep their original keys.
        k1 = oracle.get_or_create_master_key("owner-1")
        k2 = oracle.get_or_create_master_key("owner-2")
        assert k1 != k2
