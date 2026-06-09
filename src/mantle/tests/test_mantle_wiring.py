"""Tests for `search.mantle.wiring` — production accessor + indexer builders.

These exercise the graceful-degradation contract: when any prerequisite
(encryption key, S3 client, Arango handle) is missing, the builder
returns ``None`` so callers can fall back rather than silently using
ephemeral in-memory stores.
"""

from __future__ import annotations

from unittest.mock import patch

from cryptography.fernet import Fernet

from search.mantle import wiring
from search.mantle.indexer import MantleIndexer
from search.mantle.s3_cell_store import S3CellStore


class _FakeArangoDB:
    pass


class _FakeS3Client:
    def get_object(self, **_):
        raise RuntimeError("not used in builder smoke tests")

    def put_object(self, **_):
        return {}

    def delete_object(self, **_):
        return {}

    def list_objects_v2(self, **_):
        return {"Contents": []}


def _patch_oracle_ok():
    return [
        patch(
            "search.mantle.wiring.get_encryption_key",
            create=True,
            return_value=Fernet.generate_key(),
        ),
    ]


def _patch_content_service_ok():
    return [
        patch.object(wiring, "_build_cell_store", lambda: S3CellStore(_FakeS3Client(), bucket="b")),
    ]


# ---------------------------------------------------------------------------
# build_indexer
# ---------------------------------------------------------------------------

class TestBuildIndexer:
    def test_returns_indexer_when_prereqs_satisfied(self):
        with patch.object(wiring, "_build_oracle", lambda: _FakeOracle()), \
             patch.object(wiring, "_build_cell_store", lambda: S3CellStore(_FakeS3Client(), "b")):
            indexer = wiring.build_indexer(_FakeArangoDB())
        assert isinstance(indexer, MantleIndexer)

    def test_returns_none_when_any_prereq_missing(self):
        with patch.object(wiring, "_build_oracle", lambda: None):
            assert wiring.build_indexer(_FakeArangoDB()) is None


# ---------------------------------------------------------------------------
# build_sse_indexer (Step 2.6.9)
# ---------------------------------------------------------------------------


class TestBuildSseIndexer:
    def test_returns_none_when_oracle_unavailable(self):
        from search.mantle.sse import S3PostingStore, S3StatsStore
        sse_stores = (
            S3PostingStore(_FakeS3Client(), "b"),
            S3StatsStore(_FakeS3Client(), "b"),
        )
        with patch.object(wiring, "_build_oracle", lambda: None), \
             patch.object(wiring, "_build_sse_stores", lambda: sse_stores):
            assert wiring.build_sse_indexer(_FakeArangoDB()) is None

    def test_returns_none_when_sse_stores_unavailable(self):
        with patch.object(wiring, "_build_oracle", lambda: _FakeOracle()), \
             patch.object(wiring, "_build_sse_stores", lambda: None):
            assert wiring.build_sse_indexer(_FakeArangoDB()) is None

    def test_returns_indexer_when_prereqs_satisfied(self):
        from search.mantle.sse import S3PostingStore, S3StatsStore, SseIndexer
        sse_stores = (
            S3PostingStore(_FakeS3Client(), "b"),
            S3StatsStore(_FakeS3Client(), "b"),
        )
        with patch.object(wiring, "_build_oracle", lambda: _FakeOracle()), \
             patch.object(wiring, "_build_sse_stores", lambda: sse_stores):
            indexer = wiring.build_sse_indexer(_FakeArangoDB())
        assert isinstance(indexer, SseIndexer)


# ---------------------------------------------------------------------------
# build_unified_accessor (Step 2.6.9)
# ---------------------------------------------------------------------------


class TestBuildSseSearchAccessor:
    def test_returns_none_when_unified_unavailable(self):
        with patch.object(wiring, "build_unified_accessor", lambda *a, **kw: None):
            assert wiring.build_sse_search_accessor(_FakeArangoDB()) is None

    def test_returns_router_accessor_when_unified_ok(self):
        from search.mantle.sse import MantleSseSearchAccessor, MantleUnifiedAccessor
        # Build a stub unified accessor that satisfies the type check.
        # MantleUnifiedAccessor accepts an SseQueryEngine that just needs
        # to be present; using a sentinel wrapper instead of the full
        # construction chain.
        sentinel = object.__new__(MantleUnifiedAccessor)
        sentinel._sse = None  # type: ignore[attr-defined]
        sentinel._mantle = None  # type: ignore[attr-defined]
        sentinel._rrf_k = 60  # type: ignore[attr-defined]
        with patch.object(wiring, "build_unified_accessor", lambda *a, **kw: sentinel):
            acc = wiring.build_sse_search_accessor(_FakeArangoDB())
        assert isinstance(acc, MantleSseSearchAccessor)


class TestBuildUnifiedAccessor:
    def test_returns_none_when_sse_stores_missing(self):
        with patch.object(wiring, "_build_oracle", lambda: _FakeOracle()), \
             patch.object(wiring, "_build_sse_stores", lambda: None):
            assert wiring.build_unified_accessor(_FakeArangoDB()) is None

    def test_returns_none_when_oracle_missing(self):
        from search.mantle.sse import S3PostingStore, S3StatsStore
        sse_stores = (
            S3PostingStore(_FakeS3Client(), "b"),
            S3StatsStore(_FakeS3Client(), "b"),
        )
        with patch.object(wiring, "_build_oracle", lambda: None), \
             patch.object(wiring, "_build_sse_stores", lambda: sse_stores):
            assert wiring.build_unified_accessor(_FakeArangoDB()) is None

    def test_returns_accessor_with_vector_arm_when_full_prereqs(self):
        from search.mantle.sse import (
            MantleUnifiedAccessor, S3PostingStore, S3StatsStore,
        )
        sse_stores = (
            S3PostingStore(_FakeS3Client(), "b"),
            S3StatsStore(_FakeS3Client(), "b"),
        )
        with patch.object(wiring, "_build_oracle", lambda: _FakeOracle()), \
             patch.object(wiring, "_build_sse_stores", lambda: sse_stores), \
             patch.object(
                 wiring, "_build_cell_store",
                 lambda: S3CellStore(_FakeS3Client(), "b"),
             ):
            acc = wiring.build_unified_accessor(_FakeArangoDB())
        assert isinstance(acc, MantleUnifiedAccessor)
        # Vector arm wired up.
        assert acc._mantle is not None

    def test_falls_back_to_sse_only_when_vector_stores_missing(self):
        from search.mantle.sse import (
            MantleUnifiedAccessor, S3PostingStore, S3StatsStore,
        )
        sse_stores = (
            S3PostingStore(_FakeS3Client(), "b"),
            S3StatsStore(_FakeS3Client(), "b"),
        )
        with patch.object(wiring, "_build_oracle", lambda: _FakeOracle()), \
             patch.object(wiring, "_build_sse_stores", lambda: sse_stores), \
             patch.object(wiring, "_build_cell_store", lambda: None):
            acc = wiring.build_unified_accessor(_FakeArangoDB())
        assert isinstance(acc, MantleUnifiedAccessor)
        # Vector arm absent — SSE-only fusion.
        assert acc._mantle is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeOracle:
    """Minimal stand-in for OracleService — wiring only checks for non-None."""
