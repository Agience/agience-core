"""Tests for `search.mantle.sse.unified.MantleUnifiedAccessor` (Step 2.6.8).

Coverage:

- Empty inputs: empty contexts, top_k=0, both arms return nothing.
- SSE-only path: no mantle_engine wired, search returns SSE hits via RRF.
- Vector-only path: query has no SSE matches; MANTLE matches still
  produce ranked output.
- RRF fusion math: artifact in both arms gets two contributions,
  artifact in one gets one, ranking matches sum.
- MANTLE chunk ? artifact collapse: multiple chunks of one artifact
  contribute as a single best-score artifact-level hit.
- SSE multi-collection collapse: same artifact in two authorized
  collections collapses to one fused hit (best collection wins).
- Source tagging: "sse", "vector", "both".
- top_k truncation; descending sort by rrf_score.
- Vector-arm errors don't fail the search (SSE-only fallback).
- Constructor validation (rrf_k must be positive).
"""

from __future__ import annotations


import pytest
from cryptography.fernet import Fernet

from search.mantle.engine import MantleHit, MantleQueryEngine
from search.mantle.oracle import FernetMasterKeyStore, OracleService
from search.mantle.sse import (
    MantleUnifiedAccessor,
    InMemoryPostingStore,
    InMemoryStatsStore,
    SseHit,
    SseIndexer,
    SseQueryEngine,
)
from search.mantle.sse.unified import _collapse_mantle_hits_to_artifact, _rrf_fuse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def oracle() -> OracleService:
    fernet = Fernet(Fernet.generate_key())
    return OracleService(FernetMasterKeyStore(fernet))


@pytest.fixture
def posting_store() -> InMemoryPostingStore:
    return InMemoryPostingStore()


@pytest.fixture
def stats_store() -> InMemoryStatsStore:
    return InMemoryStatsStore()


@pytest.fixture
def indexer(oracle, posting_store, stats_store) -> SseIndexer:
    return SseIndexer(oracle, posting_store, stats_store)


@pytest.fixture
def sse_engine(oracle, posting_store, stats_store) -> SseQueryEngine:
    return SseQueryEngine(oracle, posting_store, stats_store)


def _mantle_hit(
    artifact_id: str, chunk_id: int, score: float,
    *, principal_id: str = "owner-A", collection_id: str = "col-1",
) -> MantleHit:
    return MantleHit(
        artifact_id=artifact_id, chunk_id=chunk_id, score=score,
        principal_id=principal_id, collection_id=collection_id,
    )


def _sse_hit(
    artifact_id: str, score: float,
    *, principal_id: str = "owner-A", collection_id: str = "col-1",
) -> SseHit:
    return SseHit(
        artifact_id=artifact_id, collection_id=collection_id,
        principal_id=principal_id, score=score,
    )


# ---------------------------------------------------------------------------
# _collapse_mantle_hits_to_artifact
# ---------------------------------------------------------------------------


class TestCollapseMantleHits:
    def test_empty(self):
        assert _collapse_mantle_hits_to_artifact([]) == []

    def test_keeps_single_chunk(self):
        h = _mantle_hit("art-1", 0, 0.9)
        out = _collapse_mantle_hits_to_artifact([h])
        assert out == [h]

    def test_collapses_multiple_chunks_best_score(self):
        # Same artifact, two chunks: the higher-scoring chunk wins.
        out = _collapse_mantle_hits_to_artifact([
            _mantle_hit("art-1", 0, 0.5),
            _mantle_hit("art-1", 1, 0.9),
            _mantle_hit("art-1", 2, 0.7),
        ])
        assert len(out) == 1
        assert out[0].artifact_id == "art-1"
        assert out[0].score == 0.9
        # Best-chunk identity is preserved.
        assert out[0].chunk_id == 1

    def test_distinct_artifacts_preserved(self):
        out = _collapse_mantle_hits_to_artifact([
            _mantle_hit("art-1", 0, 0.9),
            _mantle_hit("art-2", 0, 0.5),
            _mantle_hit("art-1", 1, 0.7),
        ])
        ids = {h.artifact_id for h in out}
        assert ids == {"art-1", "art-2"}


# ---------------------------------------------------------------------------
# _rrf_fuse
# ---------------------------------------------------------------------------


class TestRrfFuse:
    def test_empty_both_arms(self):
        assert _rrf_fuse([], []) == []

    def test_sse_only(self):
        sse = [_sse_hit("art-1", 5.0), _sse_hit("art-2", 3.0)]
        fused = _rrf_fuse(sse, [])
        assert [h.artifact_id for h in fused] == ["art-1", "art-2"]
        # rrf_score ranks: 1 ? 1/(60+1), 2 ? 1/(60+2).
        assert fused[0].rrf_score == pytest.approx(1 / 61, rel=1e-9)
        assert fused[1].rrf_score == pytest.approx(1 / 62, rel=1e-9)
        # Source tagging.
        assert all(h.source == "sse" for h in fused)
        # vector_score is None for SSE-only artifacts.
        assert all(h.vector_score is None for h in fused)
        # sse_score carries the underlying value.
        assert fused[0].sse_score == 5.0

    def test_vector_only(self):
        mantle_hits = [
            _mantle_hit("art-1", 0, 0.9),
            _mantle_hit("art-2", 0, 0.5),
        ]
        fused = _rrf_fuse([], mantle_hits)
        assert [h.artifact_id for h in fused] == ["art-1", "art-2"]
        assert all(h.source == "vector" for h in fused)
        assert all(h.sse_score is None for h in fused)
        assert fused[0].vector_score == 0.9

    def test_both_arms_overlap_sums_contributions(self):
        # art-1 ranks #1 in SSE and #2 in MANTLE ? two contributions.
        # art-2 ranks #1 in MANTLE only ? one contribution.
        # art-3 ranks #2 in SSE only ? one contribution.
        sse = [_sse_hit("art-1", 5.0), _sse_hit("art-3", 3.0)]
        mantle_hits = [_mantle_hit("art-2", 0, 0.9), _mantle_hit("art-1", 0, 0.5)]
        fused = _rrf_fuse(sse, mantle_hits)
        by_id = {h.artifact_id: h for h in fused}

        # art-1: 1/61 + 1/62
        # art-2: 1/61
        # art-3: 1/62
        assert by_id["art-1"].rrf_score == pytest.approx(
            1 / 61 + 1 / 62, rel=1e-9
        )
        assert by_id["art-2"].rrf_score == pytest.approx(1 / 61, rel=1e-9)
        assert by_id["art-3"].rrf_score == pytest.approx(1 / 62, rel=1e-9)

        # art-1 should rank above art-2 and art-3 (sum > either individual).
        assert fused[0].artifact_id == "art-1"

        # Source tagging.
        assert by_id["art-1"].source == "both"
        assert by_id["art-2"].source == "vector"
        assert by_id["art-3"].source == "sse"

        # Both scores carried for the dual-arm hit.
        assert by_id["art-1"].sse_score == 5.0
        assert by_id["art-1"].vector_score == 0.5

    def test_descending_order(self):
        sse = [_sse_hit("art-1", 5.0), _sse_hit("art-2", 3.0), _sse_hit("art-3", 1.0)]
        fused = _rrf_fuse(sse, [])
        scores = [h.rrf_score for h in fused]
        assert scores == sorted(scores, reverse=True)

    def test_mantle_chunks_collapsed_before_fusion(self):
        # Two chunks of art-1 in MANTLE � should count as one MANTLE rank,
        # not two.
        mantle_hits = [
            _mantle_hit("art-1", 0, 0.9),
            _mantle_hit("art-1", 1, 0.85),
            _mantle_hit("art-2", 0, 0.5),
        ]
        fused = _rrf_fuse([], mantle_hits)
        # Two distinct artifacts; art-1 ranks first (best chunk = 0.9).
        assert [h.artifact_id for h in fused] == ["art-1", "art-2"]
        # Just one entry per artifact even though art-1 had 2 chunks.
        assert len(fused) == 2

    def test_sse_multi_collection_collapsed(self):
        # Same artifact in two authorized collections � best collection
        # score wins, single entry.
        sse = [
            _sse_hit("art-1", 3.0, collection_id="col-1"),
            _sse_hit("art-1", 5.0, collection_id="col-2"),
        ]
        fused = _rrf_fuse(sse, [])
        assert len(fused) == 1
        # The winning collection_id is preserved.
        assert fused[0].collection_id == "col-2"
        assert fused[0].sse_score == 5.0

    def test_rrf_k_validation(self):
        with pytest.raises(ValueError, match="positive"):
            _rrf_fuse([], [], k=0)
        with pytest.raises(ValueError, match="positive"):
            _rrf_fuse([], [], k=-1)


# ---------------------------------------------------------------------------
# MantleUnifiedAccessor � end-to-end
# ---------------------------------------------------------------------------


class TestUnifiedAccessor:
    def test_constructor_validates_rrf_k(self, sse_engine):
        with pytest.raises(ValueError, match="positive"):
            MantleUnifiedAccessor(sse_engine, rrf_k=0)

    def test_empty_contexts_returns_empty(self, sse_engine):
        acc = MantleUnifiedAccessor(sse_engine)
        assert acc.search("anything", []) == []

    def test_top_k_zero(self, sse_engine):
        acc = MantleUnifiedAccessor(sse_engine)
        assert acc.search("anything", [("owner-A", "col-1")], top_k=0) == []

    def test_sse_only_no_mantle_engine(self, sse_engine, indexer):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "encryption library"},
        )
        indexer.index_artifact(
            "owner-A", "col-1", "art-2", {"title": "library cards"},
        )
        acc = MantleUnifiedAccessor(sse_engine)  # no mantle_engine
        hits = acc.search(
            "library", [("owner-A", "col-1")],
        )
        assert {h.artifact_id for h in hits} == {"art-1", "art-2"}
        assert all(h.source == "sse" for h in hits)
        assert all(h.vector_score is None for h in hits)

    def test_sse_only_when_no_query_embedding(
        self, sse_engine, indexer, oracle,
    ):
        # MANTLE engine wired but no embedding passed ? SSE-only fallback.
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "encryption"},
        )
        mantle_engine = MantleQueryEngine(oracle)  # no stores wired
        acc = MantleUnifiedAccessor(sse_engine, mantle_engine=mantle_engine)
        hits = acc.search("encryption", [("owner-A", "col-1")])
        assert len(hits) == 1
        assert hits[0].source == "sse"

    def test_top_k_truncates(self, sse_engine, indexer):
        # 3 distinct matches; ask for top_k=1.
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "library"},
        )
        indexer.index_artifact(
            "owner-A", "col-1", "art-2", {"title": "library"},
        )
        indexer.index_artifact(
            "owner-A", "col-1", "art-3", {"title": "library"},
        )
        acc = MantleUnifiedAccessor(sse_engine)
        hits = acc.search(
            "library", [("owner-A", "col-1")], top_k=1,
        )
        assert len(hits) == 1

    def test_descending_order_by_rrf_score(self, sse_engine, indexer):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "alpha beta gamma delta"},
        )
        indexer.index_artifact(
            "owner-A", "col-1", "art-2", {"title": "alpha beta"},
        )
        acc = MantleUnifiedAccessor(sse_engine)
        hits = acc.search(
            "alpha beta gamma", [("owner-A", "col-1")],
        )
        scores = [h.rrf_score for h in hits]
        assert scores == sorted(scores, reverse=True)

    def test_vector_arm_error_falls_back_to_sse(
        self, sse_engine, indexer,
    ):
        """If the vector arm raises, the search must still complete via
        the SSE arm � vector-arm errors are not search-time errors."""
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "encryption"},
        )

        class BoomMantleEngine:
            def search(self, *args, **kwargs):
                raise RuntimeError("vector arm down")

        acc = MantleUnifiedAccessor(sse_engine, mantle_engine=BoomMantleEngine())
        hits = acc.search(
            "encryption", [("owner-A", "col-1")],
            query_embedding=[0.1, 0.2, 0.3],
        )
        # Even though the vector arm failed, SSE provided a hit.
        assert len(hits) == 1
        assert hits[0].artifact_id == "art-1"
        assert hits[0].source == "sse"

    def test_no_matches_anywhere_returns_empty(self, sse_engine, indexer):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "alpha"},
        )
        acc = MantleUnifiedAccessor(sse_engine)
        hits = acc.search("zebra", [("owner-A", "col-1")])
        assert hits == []
