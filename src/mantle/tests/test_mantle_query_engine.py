"""Integration tests for `search.mantle.MantleQueryEngine` (Step 2.3).

The engine iterates over authorized (owner, collection) pairs, decrypts
each cell, and runs cosine ANN across the union. Tests use in-memory
store implementations with a real OracleService — no S3, no clustering.

Coverage:

- Empty input / unauthorized-context handling
- Single-collection, single-owner search
- Multi-collection search (different cells, different keys)
- Multi-owner authorization (results scoped to caller's contexts)
- Top-k truncation honored
- Dedup by (artifact_id, chunk_id) — best score wins across cells
- Cell cache: hit avoids re-decryption; miss re-fetches; expiry triggers reload
- Cells with mismatched embedding dimensions are skipped silently
- Cells that fail GCM auth (tampering) skip without crashing the search
- Validation: empty query / zero-norm query / missing stores
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from cryptography.fernet import Fernet

from search.mantle import MantleIndexer, MantleQueryEngine, OracleService
from search.mantle.engine import MantleHit
from search.mantle.oracle import FernetMasterKeyStore
from search.mantle.stores import InMemoryCellStore


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _live_anchorset():
    """Install a single-anchor live AnchorSet so routing is deterministic — every
    dim-16 vector routes to the one anchor's cell. The engine mechanics under
    test (decrypt, score, dedup, cache, resilience) don't depend on routing
    fan-out; test_anchors covers multi-anchor routing separation.
    """
    from search.anchors import store
    from search.anchors.anchorset import AnchorSet
    from search.anchors.repo import InMemoryAnchorRepo

    store.set_anchor_repo(InMemoryAnchorRepo())
    aset = AnchorSet("hf:test@1.0", 16)
    aset.add_text("anchor-0", np.ones(16, dtype=np.float32))
    store.save_live_anchorset(aset)
    yield
    store.set_anchor_repo(None)


@pytest.fixture
def stack():
    """Return a tuple (indexer, engine) sharing the same oracle + stores."""
    oracle = OracleService(FernetMasterKeyStore(Fernet(Fernet.generate_key())))
    cells = InMemoryCellStore()
    indexer = MantleIndexer(oracle, cells)
    engine = MantleQueryEngine(oracle, cells)
    return indexer, engine


def _vec(seed: int, dim: int = 16) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).tolist()


def _sole_cluster(cells, principal_id: str, collection_id: str) -> str:
    """The single routing-anchor cluster a single-chunk artifact occupies."""
    clusters = cells.list_clusters(principal_id, collection_id)
    assert len(clusters) == 1, f"expected one cluster, got {clusters}"
    return clusters[0]


def _chunk(artifact_id: str, chunk_id: int, *, vec_seed: int = 0, dim: int = 16, **extra) -> dict:
    return {
        "artifact_id": artifact_id,
        "chunk_id": chunk_id,
        "embedding": _vec(vec_seed, dim),
        **extra,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_empty_authorized_contexts_returns_empty(self, stack):
        _, engine = stack
        assert engine.search(_vec(0), []) == []

    def test_top_k_zero_returns_empty(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("a", 0, vec_seed=1)])
        result = engine.search(_vec(1), [("o-1", "col-A")], top_k=0)
        assert result == []

    def test_unknown_owner_yields_empty(self, stack):
        _, engine = stack
        assert engine.search(_vec(0), [("owner-ghost", "col-X")]) == []

    def test_empty_query_rejected(self, stack):
        _, engine = stack
        with pytest.raises(ValueError, match="non-empty"):
            engine.search([], [("o-1", "col-A")])

    def test_zero_norm_query_rejected(self, stack):
        _, engine = stack
        with pytest.raises(ValueError, match="zero norm"):
            engine.search([0.0] * 16, [("o-1", "col-A")])

    def test_2d_query_rejected(self, stack):
        _, engine = stack
        with pytest.raises(ValueError, match="non-empty"):
            engine.search([[1.0, 2.0], [3.0, 4.0]], [("o-1", "col-A")])

    def test_missing_stores_rejected(self):
        oracle = OracleService(FernetMasterKeyStore(Fernet(Fernet.generate_key())))
        engine = MantleQueryEngine(oracle, cell_store=None)
        with pytest.raises(ValueError, match="cell_store"):
            engine.search(_vec(0), [("o-1", "col-A")])


# ---------------------------------------------------------------------------
# Single-cell search
# ---------------------------------------------------------------------------

class TestSingleCellSearch:
    def test_finds_indexed_chunk(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        results = engine.search(_vec(1), [("o-1", "col-A")])
        assert len(results) == 1
        assert results[0].artifact_id == "art-1"
        assert results[0].chunk_id == 0
        assert results[0].score == pytest.approx(1.0, abs=1e-4)

    def test_score_is_cosine_similarity(self, stack):
        indexer, engine = stack
        indexer.index_artifact(
            "o-1", "col-A",
            [
                _chunk("art-1", 0, vec_seed=1),
                _chunk("art-2", 0, vec_seed=999),
            ],
        )
        results = engine.search(_vec(1), [("o-1", "col-A")])
        for hit in results:
            assert -1.0 <= hit.score <= 1.0
        assert results[0].artifact_id == "art-1"

    def test_top_k_truncates(self, stack):
        indexer, engine = stack
        chunks = [_chunk(f"art-{i}", 0, vec_seed=i) for i in range(10)]
        indexer.index_artifact("o-1", "col-A", chunks)
        results = engine.search(_vec(0), [("o-1", "col-A")], top_k=3)
        assert len(results) <= 3

    def test_results_ordered_by_descending_score(self, stack):
        indexer, engine = stack
        chunks = [_chunk(f"art-{i}", 0, vec_seed=i) for i in range(10)]
        indexer.index_artifact("o-1", "col-A", chunks)
        results = engine.search(_vec(0), [("o-1", "col-A")], top_k=10)
        scores = [h.score for h in results]
        assert scores == sorted(scores, reverse=True)

    def test_hits_carry_owner_and_collection(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        [hit] = engine.search(_vec(1), [("o-1", "col-A")])
        assert hit.principal_id == "o-1"
        assert hit.collection_id == "col-A"


# ---------------------------------------------------------------------------
# Multi-collection
# ---------------------------------------------------------------------------

class TestMultiCollection:
    def test_dedup_picks_best_score_across_collections(self, stack):
        """Same (artifact_id, chunk_id) in two collections — higher score wins."""
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        indexer.index_artifact("o-1", "col-B", [_chunk("art-1", 0, vec_seed=2)])
        results = engine.search(_vec(1), [("o-1", "col-A"), ("o-1", "col-B")])
        assert len(results) == 1
        assert results[0].collection_id == "col-A"

    def test_results_scoped_to_authorized_contexts(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-A", 0, vec_seed=1)])
        indexer.index_artifact("o-1", "col-B", [_chunk("art-B", 0, vec_seed=1)])
        results = engine.search(_vec(1), [("o-1", "col-A")])
        ids = {h.artifact_id for h in results}
        assert ids == {"art-A"}

    def test_no_authorized_contexts_blocks_everything(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        assert engine.search(_vec(1), []) == []


# ---------------------------------------------------------------------------
# Multi-owner
# ---------------------------------------------------------------------------

class TestMultiOwner:
    def test_owner_a_results_excluded_when_only_b_authorized(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-A", "col-X", [_chunk("art-1", 0, vec_seed=1)])
        indexer.index_artifact("o-B", "col-X", [_chunk("art-2", 0, vec_seed=1)])
        results = engine.search(_vec(1), [("o-B", "col-X")])
        ids = {h.artifact_id for h in results}
        assert ids == {"art-2"}

    def test_owner_isolation_across_search(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-A", "col-X", [_chunk("secret", 0, vec_seed=42)])
        indexer.index_artifact("o-B", "col-X", [_chunk("public", 0, vec_seed=42)])
        results = engine.search(_vec(42), [("o-B", "col-X")])
        artifact_ids = {h.artifact_id for h in results}
        assert "secret" not in artifact_ids
        assert "public" in artifact_ids


# ---------------------------------------------------------------------------
# Cell cache
# ---------------------------------------------------------------------------

class TestCellCache:
    def test_cache_hit_avoids_decryption(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        first = engine.search(_vec(1), [("o-1", "col-A")])
        # Corrupt the stored blob — cache should serve stale plaintext.
        cluster = _sole_cluster(engine._cells, "o-1", "col-A")
        engine._cells.put("o-1", "col-A", b"\x00" * 64, cluster)
        second = engine.search(_vec(1), [("o-1", "col-A")])
        assert {h.artifact_id for h in first} == {h.artifact_id for h in second}

    def test_evict_cache_forces_reload(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        engine.search(_vec(1), [("o-1", "col-A")])
        # Corrupt + evict → decrypt fails → empty results.
        cluster = _sole_cluster(engine._cells, "o-1", "col-A")
        engine._cells.put("o-1", "col-A", b"\x00" * 64, cluster)
        engine.evict_cache()
        assert engine.search(_vec(1), [("o-1", "col-A")]) == []

    def test_cache_expiry_triggers_reload(self):
        oracle = OracleService(FernetMasterKeyStore(Fernet(Fernet.generate_key())))
        cells = InMemoryCellStore()
        indexer = MantleIndexer(oracle, cells)
        engine = MantleQueryEngine(oracle, cells, cell_cache_ttl_s=0)
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        first = engine.search(_vec(1), [("o-1", "col-A")])
        time.sleep(0.05)
        second = engine.search(_vec(1), [("o-1", "col-A")])
        assert first == second

    def test_evict_specific_entry(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        engine.search(_vec(1), [("o-1", "col-A")])
        engine.evict_cache("o-1", "col-A")
        # No exception; re-decrypts on next call.
        results = engine.search(_vec(1), [("o-1", "col-A")])
        assert len(results) == 1

    def test_evict_partial_args_rejected(self, stack):
        _, engine = stack
        with pytest.raises(ValueError, match="principal_id and collection_id"):
            engine.evict_cache(principal_id="o-1")


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------

class TestResilience:
    def test_tampered_cell_does_not_crash_search(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        cluster = _sole_cluster(engine._cells, "o-1", "col-A")
        engine._cells.put("o-1", "col-A", b"\x00" * 64, cluster)
        engine.evict_cache()
        assert engine.search(_vec(1), [("o-1", "col-A")]) == []

    def test_missing_cell_does_not_crash_search(self, stack):
        # Auth context present but no data — returns empty.
        _, engine = stack
        assert engine.search(_vec(0), [("o-1", "col-A")]) == []

    def test_chunk_with_mismatched_embedding_dim_skipped(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        from search.mantle.cell import cell_aad, pack_cell, unpack_cell
        cluster = _sole_cluster(engine._cells, "o-1", "col-A")
        aad = cell_aad("col-A", cluster)
        key = engine._oracle.derive_cell_key("o-1", "col-A", cluster)
        existing = unpack_cell(engine._cells.get("o-1", "col-A", cluster), key, collection_id=aad)
        existing.append({"artifact_id": "art-bad", "chunk_id": 0, "embedding": [0.5, 0.5]})
        engine._cells.put("o-1", "col-A", pack_cell(existing, key, collection_id=aad), cluster)
        engine.evict_cache()
        results = engine.search(_vec(1), [("o-1", "col-A")])
        ids = {h.artifact_id for h in results}
        assert "art-1" in ids
        assert "art-bad" not in ids

    def test_chunk_with_zero_norm_embedding_skipped(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        from search.mantle.cell import cell_aad, pack_cell, unpack_cell
        cluster = _sole_cluster(engine._cells, "o-1", "col-A")
        aad = cell_aad("col-A", cluster)
        key = engine._oracle.derive_cell_key("o-1", "col-A", cluster)
        existing = unpack_cell(engine._cells.get("o-1", "col-A", cluster), key, collection_id=aad)
        existing.append({"artifact_id": "art-zero", "chunk_id": 0, "embedding": [0.0] * 16})
        engine._cells.put("o-1", "col-A", pack_cell(existing, key, collection_id=aad), cluster)
        engine.evict_cache()
        results = engine.search(_vec(1), [("o-1", "col-A")])
        ids = {h.artifact_id for h in results}
        assert "art-zero" not in ids


# ---------------------------------------------------------------------------
# MantleHit shape
# ---------------------------------------------------------------------------

class TestHitShape:
    def test_hit_is_immutable(self, stack):
        indexer, engine = stack
        indexer.index_artifact("o-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        [hit] = engine.search(_vec(1), [("o-1", "col-A")])
        assert isinstance(hit, MantleHit)
        with pytest.raises(Exception):
            hit.score = 999  # type: ignore  (frozen dataclass)
