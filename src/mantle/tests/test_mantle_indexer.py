"""Integration tests for `search.mantle.MantleIndexer` (Step 2.2b.iii).

The indexer composes OracleService, cell crypto, and abstract stores.
Tests use in-memory store implementations so we can verify the full
read-modify-write pipeline without touching S3.

Coverage:

- index_artifact round-trip — chunks decrypt back to themselves
- Multiple artifacts in the same cell co-exist
- Multiple chunks per artifact upsert correctly
- Chunks for different collections produce separate cells (different keys)
- remove_artifact strips chunks from the collection cell
- remove_artifact only touches the targeted collection
- Empty cells are deleted after removal
- Re-indexing the same chunk replaces (not duplicates) the record
- Validation: missing artifact_id, chunk_id, embedding all rejected
- Cells are encrypted at rest (the in-memory store holds blobs, not plaintext)
"""

from __future__ import annotations

import os

import numpy as np
import pytest
from cryptography.fernet import Fernet

from search.mantle import MantleIndexer
from search.mantle.cell import unpack_cell
from search.mantle.oracle import FernetMasterKeyStore, OracleService
from search.mantle.stores import InMemoryCellStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _live_anchorset():
    """Install a single-anchor live AnchorSet so routing is deterministic — every
    dim-16 chunk lands in the one anchor's cell. The indexer mechanics under test
    (crypto, read-modify-write, removal) don't depend on routing fan-out;
    test_anchors covers multi-anchor separation.
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
def indexer() -> MantleIndexer:
    oracle = OracleService(FernetMasterKeyStore(Fernet(Fernet.generate_key())))
    return MantleIndexer(
        oracle=oracle,
        cell_store=InMemoryCellStore(),
    )


def _vec(seed: int, dim: int = 16) -> list[float]:
    """Deterministic vector for repeatable tests."""
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).tolist()


def _sole_cluster(cells, principal_id: str, collection_id: str) -> str:
    """The single routing-anchor cluster a collection's cells occupy in these
    one-anchor tests (a single-chunk artifact lands in exactly one cell)."""
    clusters = cells.list_clusters(principal_id, collection_id)
    assert len(clusters) == 1, f"expected one cluster, got {clusters}"
    return clusters[0]


def _chunk(artifact_id: str, chunk_id: int, *, vec_seed: int = 0, **extra) -> dict:
    return {
        "artifact_id": artifact_id,
        "chunk_id": chunk_id,
        "embedding": _vec(vec_seed),
        **extra,
    }


# ---------------------------------------------------------------------------
# index_artifact
# ---------------------------------------------------------------------------

class TestIndexArtifact:
    def test_chunk_round_trips_through_cell(self, indexer):
        chunks = [
            _chunk("art-1", 0, vec_seed=1, tokens=42),
            _chunk("art-1", 1, vec_seed=2, tokens=37),
        ]
        indexer.index_artifact("owner-1", "col-A", chunks)
        recovered = indexer.collection_chunks("owner-1", "col-A")
        assert len(recovered) == 2
        artifact_chunks = sorted(recovered, key=lambda c: c["chunk_id"])
        assert artifact_chunks[0]["tokens"] == 42
        assert artifact_chunks[1]["tokens"] == 37

    def test_multiple_artifacts_share_cell(self, indexer):
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-1", 0, vec_seed=0)])
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-2", 0, vec_seed=1)])
        all_chunks = indexer.collection_chunks("owner-1", "col-A")
        artifact_ids = {c["artifact_id"] for c in all_chunks}
        assert artifact_ids == {"art-1", "art-2"}

    def test_re_indexing_replaces_not_duplicates(self, indexer):
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-1", 0, vec_seed=1, tokens=10)])
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-1", 0, vec_seed=1, tokens=20)])
        all_chunks = indexer.collection_chunks("owner-1", "col-A")
        assert len(all_chunks) == 1
        assert all_chunks[0]["tokens"] == 20

    def test_different_collections_get_separate_cells(self, indexer):
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-1", 0, vec_seed=5)])
        indexer.index_artifact("owner-1", "col-B", [_chunk("art-2", 0, vec_seed=5)])
        cells = indexer.cells_for("owner-1")
        assert set(cells) == {"col-A", "col-B"}

    def test_empty_chunk_list_is_no_op(self, indexer):
        result = indexer.index_artifact("owner-1", "col-A", [])
        assert result == 0
        assert indexer.cells_for("owner-1") == []

    def test_validation_rejects_missing_keys(self, indexer):
        with pytest.raises(ValueError, match="artifact_id"):
            indexer.index_artifact(
                "owner-1", "col-A",
                [{"chunk_id": 0, "embedding": _vec(0)}],
            )
        with pytest.raises(ValueError, match="embedding"):
            indexer.index_artifact(
                "owner-1", "col-A",
                [{"artifact_id": "x", "chunk_id": 0}],
            )

    def test_validation_rejects_non_dict(self, indexer):
        with pytest.raises(ValueError, match="dict"):
            indexer.index_artifact("owner-1", "col-A", ["not a dict"])

    def test_rejects_empty_owner_or_collection(self, indexer):
        with pytest.raises(ValueError):
            indexer.index_artifact("", "col-A", [_chunk("a", 0)])
        with pytest.raises(ValueError):
            indexer.index_artifact("owner-1", "", [_chunk("a", 0)])

    def test_returns_1_when_cell_touched(self, indexer):
        result = indexer.index_artifact("owner-1", "col-A", [_chunk("art-1", 0)])
        assert result == 1


# ---------------------------------------------------------------------------
# remove_artifact
# ---------------------------------------------------------------------------

class TestRemoveArtifact:
    def test_removes_artifact_chunks(self, indexer):
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-2", 0, vec_seed=2)])
        touched = indexer.remove_artifact("owner-1", "col-A", "art-1")
        assert touched == 1
        remaining = {c["artifact_id"] for c in indexer.collection_chunks("owner-1", "col-A")}
        assert remaining == {"art-2"}

    def test_removing_only_artifact_deletes_cell(self, indexer):
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-only", 0, vec_seed=1)])
        indexer.remove_artifact("owner-1", "col-A", "art-only")
        assert indexer.cells_for("owner-1") == []

    def test_remove_unknown_artifact_is_no_op(self, indexer):
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        touched = indexer.remove_artifact("owner-1", "col-A", "ghost")
        assert touched == 0
        assert len(indexer.collection_chunks("owner-1", "col-A")) == 1

    def test_remove_only_touches_target_collection(self, indexer):
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        indexer.index_artifact("owner-1", "col-B", [_chunk("art-1", 0, vec_seed=1)])
        indexer.remove_artifact("owner-1", "col-A", "art-1")
        assert "col-A" not in indexer.cells_for("owner-1")
        assert "col-B" in indexer.cells_for("owner-1")

    def test_remove_validation(self, indexer):
        with pytest.raises(ValueError):
            indexer.remove_artifact("", "col-A", "art-1")
        with pytest.raises(ValueError):
            indexer.remove_artifact("owner-1", "", "art-1")
        with pytest.raises(ValueError):
            indexer.remove_artifact("owner-1", "col-A", "")

    def test_partial_removal_re_encrypts_remaining(self, indexer):
        indexer.index_artifact(
            "owner-1", "col-A",
            [
                _chunk("art-1", 0, vec_seed=1, tokens=10),
                _chunk("art-1", 1, vec_seed=1, tokens=20),
                _chunk("art-2", 0, vec_seed=1, tokens=30),
            ],
        )
        indexer.remove_artifact("owner-1", "col-A", "art-1")
        all_chunks = indexer.collection_chunks("owner-1", "col-A")
        assert len(all_chunks) == 1
        assert all_chunks[0]["artifact_id"] == "art-2"
        assert all_chunks[0]["tokens"] == 30


# ---------------------------------------------------------------------------
# At-rest encryption
# ---------------------------------------------------------------------------

class TestAtRestEncryption:
    def test_cells_are_encrypted_in_store(self, indexer):
        indexer.index_artifact(
            "owner-1", "col-A",
            [_chunk("super-secret-artifact-id", 0, vec_seed=1)],
        )
        cluster = _sole_cluster(indexer._cells, "owner-1", "col-A")
        raw_blob = indexer._cells.get("owner-1", "col-A", cluster)
        assert raw_blob is not None
        assert b"super-secret-artifact-id" not in raw_blob
        assert b'"artifact_id"' not in raw_blob

    def test_decryption_requires_correct_collection_key(self, indexer):
        """A blob encrypted under col-A cannot be decrypted with col-B's key."""
        indexer.index_artifact("owner-1", "col-A", [_chunk("art-1", 0, vec_seed=1)])
        cluster = _sole_cluster(indexer._cells, "owner-1", "col-A")
        raw_blob = indexer._cells.get("owner-1", "col-A", cluster)
        wrong_key = indexer._oracle.derive_cell_key("owner-1", "col-B", cluster)
        from search.mantle.cell import CellTampered
        with pytest.raises(CellTampered):
            unpack_cell(raw_blob, wrong_key, collection_id="col-A")


# ---------------------------------------------------------------------------
# Multi-owner isolation
# ---------------------------------------------------------------------------

class TestMultiOwnerIsolation:
    def test_two_owners_have_independent_storage(self, indexer):
        indexer.index_artifact("owner-A", "col-X", [_chunk("art-1", 0, vec_seed=1)])
        indexer.index_artifact("owner-B", "col-X", [_chunk("art-1", 0, vec_seed=1)])
        ca = _sole_cluster(indexer._cells, "owner-A", "col-X")
        cb = _sole_cluster(indexer._cells, "owner-B", "col-X")
        a_blob = indexer._cells.get("owner-A", "col-X", ca)
        b_blob = indexer._cells.get("owner-B", "col-X", cb)
        assert a_blob is not None and b_blob is not None
        assert a_blob != b_blob

    def test_owner_a_cannot_decrypt_owner_b_cell(self, indexer):
        indexer.index_artifact("owner-A", "col-X", [_chunk("art-1", 0, vec_seed=1)])
        indexer.index_artifact("owner-B", "col-X", [_chunk("art-1", 0, vec_seed=1)])
        cb = _sole_cluster(indexer._cells, "owner-B", "col-X")
        b_blob = indexer._cells.get("owner-B", "col-X", cb)
        a_key = indexer._oracle.derive_cell_key("owner-A", "col-X", cb)
        from search.mantle.cell import CellTampered
        with pytest.raises(CellTampered):
            unpack_cell(b_blob, a_key, collection_id="col-X")


def test_os_urandom_works():
    assert len(os.urandom(32)) == 32

