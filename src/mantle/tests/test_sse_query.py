"""Tests for `search.mantle.sse.query.SseQueryEngine` (MANTLE-SSE Step 2.6.7).

Coverage:

- Empty-input short-circuits: empty query, top_k≤0, no authorized
  contexts, empty fields list → returns [].
- End-to-end: index a small corpus → search returns ranked hits.
- Authorization filter: posting entries from non-authorized collections
  are excluded.
- Multi-owner: search merges hits across owners' independent SSE keys.
- top_k truncation; ranking order preserved.
- Field selection: explicit fields parameter, zero-boost field dropped.
- Field boost actually scales scores.
- Cache: posting list cached after first fetch (modifying store after
  warmup doesn't affect a cached search); stats cached too.
- Cache invalidation by owner / global.
- Resilience: tampered posting list → silently skipped; tampered stats
  blob → owner contributes nothing.
- Missing stats (owner never indexed) → owner contributes nothing.
- Stems unify with index analysis: query "running" matches indexed
  "runs" (Porter stem).
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from search.mantle.oracle import FernetMasterKeyStore, OracleService
from search.mantle.sse import (
    InMemoryPostingStore,
    InMemoryStatsStore,
    SseHit,
    SseIndexer,
    SseQueryEngine,
    blind_tokens as bt,
)


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
def engine(oracle, posting_store, stats_store) -> SseQueryEngine:
    return SseQueryEngine(oracle, posting_store, stats_store)


def _seed_corpus(indexer: SseIndexer, owner: str = "owner-A") -> None:
    """Seed a small corpus for query tests:

      art-1 in col-1: title="encryption library"
      art-2 in col-1: title="library cards"
      art-3 in col-2: title="encryption keys"
      art-4 in col-2: title="quick brown fox" content="lazy dog jumps"
    """
    indexer.index_artifact(owner, "col-1", "art-1", {"title": "encryption library"})
    indexer.index_artifact(owner, "col-1", "art-2", {"title": "library cards"})
    indexer.index_artifact(owner, "col-2", "art-3", {"title": "encryption keys"})
    indexer.index_artifact(
        owner, "col-2", "art-4",
        {"title": "quick brown fox", "content": "lazy dog jumps"},
    )


# ---------------------------------------------------------------------------
# Short-circuits
# ---------------------------------------------------------------------------


class TestShortCircuits:
    def test_empty_query(self, engine):
        assert engine.search("", [("owner-A", "col-1")]) == []
        assert engine.search("   ", [("owner-A", "col-1")]) == []

    def test_top_k_zero_or_negative(self, engine, indexer):
        _seed_corpus(indexer)
        assert engine.search("encryption", [("owner-A", "col-1")], top_k=0) == []
        assert engine.search("encryption", [("owner-A", "col-1")], top_k=-1) == []

    def test_no_authorized_contexts(self, engine, indexer):
        _seed_corpus(indexer)
        assert engine.search("encryption", []) == []
        # Skipping owner-less / collection-less tuples.
        assert engine.search("encryption", [("", "col-1")]) == []
        assert engine.search("encryption", [("owner-A", "")]) == []

    def test_no_fields_to_search(self, engine, indexer):
        _seed_corpus(indexer)
        # All fields zero-boosted → nothing to search.
        e = SseQueryEngine(
            engine._oracle, engine._postings, engine._stats,
            field_boosts={"title": 0.0, "description": 0.0, "tags": 0.0, "content": 0.0},
        )
        assert e.search("encryption", [("owner-A", "col-1")]) == []

    def test_query_with_only_stop_words(self, engine, indexer):
        # The English analyzer drops stop words — a query of "the and" stems
        # to nothing.
        _seed_corpus(indexer)
        assert engine.search("the and", [("owner-A", "col-1")]) == []


# ---------------------------------------------------------------------------
# End-to-end basic search
# ---------------------------------------------------------------------------


class TestBasicSearch:
    def test_finds_indexed_term(self, engine, indexer):
        _seed_corpus(indexer)
        hits = engine.search(
            "encryption", [("owner-A", "col-1"), ("owner-A", "col-2")],
        )
        artifact_ids = {h.artifact_id for h in hits}
        # encryption appears in art-1 (col-1) and art-3 (col-2).
        assert artifact_ids == {"art-1", "art-3"}

    def test_returns_sse_hit_shape(self, engine, indexer):
        _seed_corpus(indexer)
        hits = engine.search("encryption", [("owner-A", "col-1")])
        assert len(hits) >= 1
        for hit in hits:
            assert isinstance(hit, SseHit)
            assert hit.principal_id == "owner-A"
            assert hit.score > 0

    def test_unmatched_query_returns_empty(self, engine, indexer):
        _seed_corpus(indexer)
        hits = engine.search(
            "zebra", [("owner-A", "col-1"), ("owner-A", "col-2")],
        )
        assert hits == []

    def test_query_stem_matches_index_stem(self, engine, indexer):
        # Index "running"; search "runs". Both stem to the same root.
        indexer.index_artifact(
            "owner-A", "col-1", "art-runs",
            {"title": "running through the park"},
        )
        hits = engine.search("runs", [("owner-A", "col-1")])
        assert len(hits) == 1
        assert hits[0].artifact_id == "art-runs"

    def test_multi_term_query(self, engine, indexer):
        _seed_corpus(indexer)
        hits = engine.search(
            "encryption library", [("owner-A", "col-1")],
        )
        # art-1 has both terms; art-2 has only "library"; both should
        # return, but art-1 should outscore art-2.
        scores = {h.artifact_id: h.score for h in hits}
        assert "art-1" in scores
        assert "art-2" in scores
        assert scores["art-1"] > scores["art-2"]


# ---------------------------------------------------------------------------
# Authorization filtering
# ---------------------------------------------------------------------------


class TestAuthorizationFilter:
    def test_filters_to_authorized_collection(self, engine, indexer):
        _seed_corpus(indexer)
        # Only authorized in col-1 — even though art-3 (in col-2) matches
        # "encryption", it shouldn't appear.
        hits = engine.search(
            "encryption", [("owner-A", "col-1")],
        )
        ids = {h.artifact_id for h in hits}
        assert "art-1" in ids
        assert "art-3" not in ids

    def test_filters_in_shared_posting_list(self, engine, indexer):
        # When a posting list contains entries from multiple collections,
        # only authorized ones contribute.
        _seed_corpus(indexer)
        # "library" appears in both art-1 (col-1) and art-2 (col-1).
        # Authorize only col-2 — neither is authorized → no hits for
        # "library".
        hits = engine.search("library", [("owner-A", "col-2")])
        assert hits == []

    def test_no_authorized_contexts_for_owner(self, engine, indexer):
        _seed_corpus(indexer)
        # Authorize a different owner only.
        hits = engine.search(
            "encryption", [("owner-B", "col-1")],
        )
        assert hits == []


# ---------------------------------------------------------------------------
# Multi-owner
# ---------------------------------------------------------------------------


class TestMultiOwner:
    def test_search_across_owners(self, engine, indexer):
        _seed_corpus(indexer, owner="owner-A")
        # Different owner has its own SSE key — same query produces
        # different blind tokens. Index "encryption" under owner-B too.
        indexer.index_artifact(
            "owner-B", "col-X", "art-B-1", {"title": "encryption protocols"},
        )
        hits = engine.search(
            "encryption",
            [("owner-A", "col-1"), ("owner-B", "col-X")],
        )
        owners = {h.principal_id for h in hits}
        assert owners == {"owner-A", "owner-B"}

    def test_owner_isolation(self, engine, indexer):
        # Indexing in owner-B does not produce hits for owner-A
        # authorization.
        indexer.index_artifact(
            "owner-B", "col-X", "art-B-1", {"title": "encryption"},
        )
        hits = engine.search(
            "encryption", [("owner-A", "col-X")],
        )
        # owner-A has no stats/postings → empty.
        assert hits == []


# ---------------------------------------------------------------------------
# Ranking + top_k
# ---------------------------------------------------------------------------


class TestRanking:
    def test_top_k_truncation(self, engine, indexer):
        _seed_corpus(indexer)
        # "encryption" matches 2 artifacts (art-1, art-3); request 1.
        hits = engine.search(
            "encryption",
            [("owner-A", "col-1"), ("owner-A", "col-2")],
            top_k=1,
        )
        assert len(hits) == 1

    def test_sorted_descending(self, engine, indexer):
        _seed_corpus(indexer)
        hits = engine.search(
            "encryption library",
            [("owner-A", "col-1"), ("owner-A", "col-2")],
        )
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Field selection + boosts
# ---------------------------------------------------------------------------


class TestFieldSelection:
    def test_explicit_fields_param(self, oracle, posting_store, stats_store, indexer):
        # art with the same word in title AND content. Limit to "content".
        indexer.index_artifact(
            "owner-A", "col-1", "art-1",
            {"title": "lazy", "content": "lazy"},
        )
        eng = SseQueryEngine(oracle, posting_store, stats_store)
        # Search title only.
        title_hits = eng.search(
            "lazy", [("owner-A", "col-1")], fields=["title"],
        )
        # Search content only.
        content_hits = eng.search(
            "lazy", [("owner-A", "col-1")], fields=["content"],
        )
        # Both should find art-1 — but if we restrict to title, the
        # content posting list doesn't contribute.
        assert {h.artifact_id for h in title_hits} == {"art-1"}
        assert {h.artifact_id for h in content_hits} == {"art-1"}
        # Title match has higher tf:dl ratio (single-token field), so
        # title-only score should differ from content-only.
        title_score = title_hits[0].score
        content_score = content_hits[0].score
        # They search different fields → different posting lists →
        # different scores (concretely: same dl=1 here, so they should
        # be equal — but if dl differed, they'd diverge). Just verify
        # both produced positive scores.
        assert title_score > 0
        assert content_score > 0

    def test_zero_boost_field_skipped(
        self, oracle, posting_store, stats_store, indexer,
    ):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1",
            {"title": "alpha", "content": "alpha"},
        )
        # Zero-boost title — but content boost stays default 1.0.
        eng = SseQueryEngine(
            oracle, posting_store, stats_store,
            field_boosts={"title": 0.0},
        )
        hits = eng.search("alpha", [("owner-A", "col-1")])
        # Found via content only.
        assert len(hits) == 1

    def test_field_boost_scales_score(
        self, oracle, posting_store, stats_store, indexer,
    ):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "alpha"},
        )
        # No boost (default 1.0).
        eng_default = SseQueryEngine(oracle, posting_store, stats_store)
        # 5x boost on title.
        eng_boosted = SseQueryEngine(
            oracle, posting_store, stats_store,
            field_boosts={"title": 5.0},
        )
        default_score = eng_default.search("alpha", [("owner-A", "col-1")])[0].score
        boosted_score = eng_boosted.search("alpha", [("owner-A", "col-1")])[0].score
        # Score scales linearly with field_boost.
        assert boosted_score == pytest.approx(5.0 * default_score, rel=1e-9)

    def test_unknown_field_in_explicit_list_ignored(
        self, oracle, posting_store, stats_store, indexer,
    ):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "alpha"},
        )
        eng = SseQueryEngine(oracle, posting_store, stats_store)
        # "garbage" isn't a known field — should be filtered, leaving title.
        hits = eng.search(
            "alpha", [("owner-A", "col-1")], fields=["title", "garbage"],
        )
        assert len(hits) == 1


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


class TestCaching:
    def test_posting_cache_warm_skips_store(
        self, oracle, posting_store, stats_store, indexer,
    ):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "alpha"},
        )
        eng = SseQueryEngine(oracle, posting_store, stats_store)
        # Warm cache.
        eng.search("alpha", [("owner-A", "col-1")])

        # Now mutate the store directly — bypass the indexer so the
        # query engine's TTL cache still satisfies the next search.
        for tok in posting_store.list_tokens_for_owner("owner-A"):
            posting_store.delete_posting("owner-A", tok)

        # Cached posting lists still satisfy the query.
        hits = eng.search("alpha", [("owner-A", "col-1")])
        assert len(hits) == 1

    def test_invalidate_caches_drops_owner(
        self, oracle, posting_store, stats_store, indexer,
    ):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "alpha"},
        )
        eng = SseQueryEngine(oracle, posting_store, stats_store)
        eng.search("alpha", [("owner-A", "col-1")])  # warm cache

        # Drop store + caches.
        for tok in posting_store.list_tokens_for_owner("owner-A"):
            posting_store.delete_posting("owner-A", tok)
        posting_store._postings.clear()  # type: ignore[attr-defined]
        stats_store.delete("owner-A")
        eng.invalidate_caches("owner-A")

        # Now the search returns empty — cache no longer hides the
        # missing data.
        assert eng.search("alpha", [("owner-A", "col-1")]) == []

    def test_invalidate_caches_global(
        self, oracle, posting_store, stats_store, indexer,
    ):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "alpha"},
        )
        eng = SseQueryEngine(oracle, posting_store, stats_store)
        eng.search("alpha", [("owner-A", "col-1")])  # warm

        # Wipe everything, invalidate globally.
        posting_store._postings.clear()  # type: ignore[attr-defined]
        stats_store.delete("owner-A")
        eng.invalidate_caches()

        assert eng.search("alpha", [("owner-A", "col-1")]) == []


# ---------------------------------------------------------------------------
# Resilience to corruption / missing data
# ---------------------------------------------------------------------------


class TestResilience:
    def test_tampered_posting_silently_skipped(
        self, oracle, posting_store, stats_store, indexer,
    ):
        # Index two artifacts so we can corrupt one posting list and
        # verify queries on others still work.
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "alpha"},
        )
        indexer.index_artifact(
            "owner-A", "col-1", "art-2", {"title": "beta"},
        )
        # Corrupt the alpha posting list.
        owner_key = oracle.derive_sse_key("owner-A")
        from search.mantle.sse.tokenizer import tokenize
        alpha_stem = tokenize("alpha")[0]
        alpha_tok = bt.blind_token(owner_key, bt.FIELD_TITLE, alpha_stem)
        # Replace with random garbage of valid blob length.
        garbage = os.urandom(40)  # > 28 bytes overhead, not a valid GCM blob
        posting_store.put_posting("owner-A", alpha_tok, garbage)

        eng = SseQueryEngine(oracle, posting_store, stats_store)

        # Query for "alpha" — corrupted posting list yields no hits.
        assert eng.search("alpha", [("owner-A", "col-1")]) == []
        # Query for "beta" — unaffected, still returns art-2.
        beta_hits = eng.search("beta", [("owner-A", "col-1")])
        assert {h.artifact_id for h in beta_hits} == {"art-2"}

    def test_tampered_stats_owner_contributes_nothing(
        self, oracle, posting_store, stats_store, indexer,
    ):
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "alpha"},
        )
        # Corrupt the stats blob.
        stats_store.put("owner-A", os.urandom(40))

        eng = SseQueryEngine(oracle, posting_store, stats_store)
        # No stats → no IDF → no score → no hit.
        assert eng.search("alpha", [("owner-A", "col-1")]) == []

    def test_owner_with_no_stats_yields_no_hits(
        self, oracle, posting_store, stats_store,
    ):
        eng = SseQueryEngine(oracle, posting_store, stats_store)
        # Owner has never been indexed — no stats blob.
        assert eng.search("alpha", [("owner-A", "col-1")]) == []


# ---------------------------------------------------------------------------
# Phrase / bigram search
# ---------------------------------------------------------------------------


class TestPhraseSearch:
    """Quoted queries use bigram posting lists for exact phrase matching."""

    def test_phrase_matches_adjacent_terms(self, engine, indexer):
        # "encryption library" — both terms adjacent → phrase match.
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "encryption library"},
        )
        indexer.index_artifact(
            "owner-A", "col-1", "art-2", {"title": "encryption keys"},
        )
        hits = engine.search(
            '"encryption library"', [("owner-A", "col-1")],
        )
        ids = {h.artifact_id for h in hits}
        assert ids == {"art-1"}
        assert "art-2" not in ids

    def test_phrase_excludes_non_adjacent_terms(self, engine, indexer):
        # art-1 has both "encryption" and "library" but NOT adjacent.
        indexer.index_artifact(
            "owner-A", "col-1", "art-1",
            {"title": "encryption", "description": "library tools"},
        )
        indexer.index_artifact(
            "owner-A", "col-1", "art-2",
            {"title": "encryption library"},
        )
        hits = engine.search(
            '"encryption library"', [("owner-A", "col-1")],
        )
        ids = {h.artifact_id for h in hits}
        # art-2 has the phrase in title; art-1 has both terms but not adjacent
        # in the same field — the bigram is not in any single field posting.
        assert "art-2" in ids
        assert "art-1" not in ids

    def test_phrase_single_term_falls_through(self, engine, indexer):
        # A single-term quoted query has no bigrams → falls through to
        # regular unigram scoring (phrase filter is a no-op).
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "encryption library"},
        )
        hits = engine.search('"encryption"', [("owner-A", "col-1")])
        assert {h.artifact_id for h in hits} == {"art-1"}

    def test_phrase_stops_word_stripped(self, engine, indexer):
        # "the library" → tokenize → ["librari"] (stop word "the" dropped)
        # → single stem → no bigrams → unigram path.
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "the library"},
        )
        hits = engine.search('"the library"', [("owner-A", "col-1")])
        assert {h.artifact_id for h in hits} == {"art-1"}

    def test_phrase_empty_after_strip_returns_empty(self, engine, indexer):
        # Quoted query that tokenizes to nothing.
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "encryption library"},
        )
        hits = engine.search('"the and"', [("owner-A", "col-1")])
        assert hits == []

    def test_unquoted_multi_term_returns_or_semantics(self, engine, indexer):
        # Unquoted: OR semantics — both artifacts match (one has each term).
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "encryption keys"},
        )
        indexer.index_artifact(
            "owner-A", "col-1", "art-2", {"title": "library cards"},
        )
        hits = engine.search(
            "encryption library", [("owner-A", "col-1")],
        )
        ids = {h.artifact_id for h in hits}
        assert "art-1" in ids
        assert "art-2" in ids

    def test_phrase_quoted_gives_and_semantics(self, engine, indexer):
        # Quoted: phrase semantics — only the artifact with the adjacent
        # pair is returned.
        indexer.index_artifact(
            "owner-A", "col-1", "art-1", {"title": "encryption keys"},
        )
        indexer.index_artifact(
            "owner-A", "col-1", "art-2", {"title": "library cards"},
        )
        hits = engine.search(
            '"encryption library"', [("owner-A", "col-1")],
        )
        # Neither artifact has "encryption" and "library" adjacent.
        assert hits == []

