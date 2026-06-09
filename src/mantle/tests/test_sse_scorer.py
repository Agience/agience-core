"""Tests for `search.mantle.sse.scorer` (MANTLE-SSE Step 2.6.5).

Coverage:

- :func:`idf` — formula correctness, df=0 / N=0 edge cases, monotonicity
  (rare term > common term).
- :func:`normalized_tf` — formula correctness, dl saturation, b-coefficient
  effect, avg_dl=0 fallback.
- :func:`bm25_term_score` — combined contribution; field-boost scaling;
  zeros where any input zeros the score.
- :func:`score_query` — aggregation across multiple TokenHits, multi-field
  combination, dedup vs (artifact_id, collection_id), missing-stats
  short-circuits, missing-field-boost defaults to 1.0, malformed-entry
  filtering, IDF=0 / df=0 short-circuits.
- Numerical sanity: rare term outscores common term; longer doc with same
  tf scores lower than shorter (length penalty).
"""

from __future__ import annotations

import math

import pytest

from search.mantle.sse import scorer
from search.mantle.sse.stats import Stats


# ---------------------------------------------------------------------------
# IDF
# ---------------------------------------------------------------------------


class TestIDF:
    def test_basic_formula(self):
        # IDF = ln((N - df + 0.5) / (df + 0.5) + 1)
        # N=100, df=10: ln((90.5 / 10.5) + 1) = ln(9.619)
        expected = math.log((100 - 10 + 0.5) / (10 + 0.5) + 1)
        assert math.isclose(scorer.idf(10, 100), expected, rel_tol=1e-12)

    def test_zero_df_returns_zero(self):
        assert scorer.idf(0, 100) == 0.0

    def test_zero_doc_count_returns_zero(self):
        assert scorer.idf(5, 0) == 0.0

    def test_negative_df_returns_zero(self):
        assert scorer.idf(-1, 100) == 0.0

    def test_rare_term_higher_than_common_term(self):
        rare = scorer.idf(2, 1000)
        common = scorer.idf(900, 1000)
        assert rare > common

    def test_non_negative_for_very_common(self):
        """The Lucene "+1 inside ln" trick keeps IDF ≥ 0 even when
        df > N/2 (where the plain formula would go negative)."""
        # df = N - 1 (extremely common) — should still be non-negative.
        for n in (10, 100, 1000):
            v = scorer.idf(n - 1, n)
            assert v >= 0.0

    def test_df_equals_doc_count(self):
        # IDF when df == N: ln(0.5 / (N+0.5) + 1) — small positive.
        v = scorer.idf(50, 50)
        assert v > 0.0
        assert v < 0.1  # Very small for a term in every document.


# ---------------------------------------------------------------------------
# normalized_tf
# ---------------------------------------------------------------------------


class TestNormalizedTF:
    def test_zero_tf_returns_zero(self):
        assert scorer.normalized_tf(0, 10, 10.0) == 0.0

    def test_negative_tf_returns_zero(self):
        assert scorer.normalized_tf(-1, 10, 10.0) == 0.0

    def test_at_average_length(self):
        """When dl == avg_dl, the (1 - b + b·dl/avgdl) factor collapses
        to 1, so nf = tf·(k1+1) / (tf+k1)."""
        tf, dl, avg = 3, 10, 10.0
        k1 = 1.2
        expected = (tf * (k1 + 1.0)) / (tf + k1)
        assert math.isclose(
            scorer.normalized_tf(tf, dl, avg, k1=k1, b=0.75),
            expected, rel_tol=1e-12,
        )

    def test_short_doc_scores_higher_than_long(self):
        """Same tf in a shorter-than-average doc → higher nf (length
        penalty rewards focused docs)."""
        nf_short = scorer.normalized_tf(2, 5, 10.0)   # half-length
        nf_long = scorer.normalized_tf(2, 20, 10.0)   # double-length
        assert nf_short > nf_long

    def test_b_zero_disables_length_norm(self):
        """With b=0, dl is irrelevant — short and long docs score the same."""
        nf_short = scorer.normalized_tf(2, 5, 10.0, b=0.0)
        nf_long = scorer.normalized_tf(2, 20, 10.0, b=0.0)
        assert math.isclose(nf_short, nf_long, rel_tol=1e-12)

    def test_avg_dl_zero_fallback(self):
        """avg_dl=0 should not divide-by-zero — falls back to no length norm."""
        v = scorer.normalized_tf(3, 10, 0.0)
        # Equivalent to b=0: tf·(k1+1) / (tf+k1).
        k1 = 1.2
        expected = (3 * (k1 + 1.0)) / (3 + k1)
        assert math.isclose(v, expected, rel_tol=1e-12)

    def test_tf_saturation(self):
        """As tf grows, nf approaches an asymptote — diminishing returns."""
        nfs = [scorer.normalized_tf(t, 10, 10.0) for t in (1, 5, 50, 500)]
        # Strictly increasing.
        assert nfs[0] < nfs[1] < nfs[2] < nfs[3]
        # But the gap shrinks.
        assert (nfs[3] - nfs[2]) < (nfs[1] - nfs[0])


# ---------------------------------------------------------------------------
# bm25_term_score (combined)
# ---------------------------------------------------------------------------


class TestBM25TermScore:
    def test_combined_formula(self):
        score = scorer.bm25_term_score(
            tf=3, dl=10, df_value=10, doc_count=100, avg_dl=10.0,
            field_boost=2.0,
        )
        expected = 2.0 * scorer.idf(10, 100) * scorer.normalized_tf(3, 10, 10.0)
        assert math.isclose(score, expected, rel_tol=1e-12)

    def test_field_boost_scales_linearly(self):
        s1 = scorer.bm25_term_score(
            tf=3, dl=10, df_value=10, doc_count=100, avg_dl=10.0,
            field_boost=1.0,
        )
        s5 = scorer.bm25_term_score(
            tf=3, dl=10, df_value=10, doc_count=100, avg_dl=10.0,
            field_boost=5.0,
        )
        assert math.isclose(s5, 5.0 * s1, rel_tol=1e-12)

    def test_zero_when_field_boost_zero(self):
        assert scorer.bm25_term_score(
            tf=3, dl=10, df_value=10, doc_count=100, avg_dl=10.0,
            field_boost=0.0,
        ) == 0.0

    def test_zero_when_no_tf(self):
        assert scorer.bm25_term_score(
            tf=0, dl=10, df_value=10, doc_count=100, avg_dl=10.0,
        ) == 0.0

    def test_zero_when_no_df(self):
        assert scorer.bm25_term_score(
            tf=3, dl=10, df_value=0, doc_count=100, avg_dl=10.0,
        ) == 0.0

    def test_zero_when_no_docs(self):
        assert scorer.bm25_term_score(
            tf=3, dl=10, df_value=5, doc_count=0, avg_dl=10.0,
        ) == 0.0


# ---------------------------------------------------------------------------
# score_query (aggregation)
# ---------------------------------------------------------------------------


@pytest.fixture
def stats_3_docs() -> Stats:
    """Stats for 3 documents.

    field_doc_count: {"title": 3, "content": 3}
    field_total_dl:  {"title": 18, "content": 600}    → avgdl_title=6, avgdl_content=200
    df: { token-rare: 1, token-common: 3, token-medium: 2 }
    """
    return Stats(
        doc_count=3,
        field_doc_count={"title": 3, "content": 3},
        field_total_dl={"title": 18, "content": 600},
        df={
            "rare" * 16: 1,
            "common" * 10 + "abcd": 3,  # 64 chars total
            "med" * 21 + "z": 2,        # 64 chars total
        },
    )


class TestScoreQuery:
    def test_empty_token_hits(self, stats_3_docs):
        scores = scorer.score_query([], stats_3_docs)
        assert scores == {}

    def test_single_hit_single_entry(self, stats_3_docs):
        token = "rare" * 16  # 64 chars; df=1
        hit = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[{"artifact_id": "a-1", "collection_id": "c-1", "tf": 2, "dl": 6}],
        )
        scores = scorer.score_query([hit], stats_3_docs)
        # One entry → one (a-1, c-1) score.
        assert list(scores.keys()) == [("a-1", "c-1")]
        expected = scorer.bm25_term_score(
            tf=2, dl=6, df_value=1, doc_count=3, avg_dl=6.0,
        )
        assert math.isclose(scores[("a-1", "c-1")], expected, rel_tol=1e-12)

    def test_field_boost_applied(self, stats_3_docs):
        token = "rare" * 16
        hit = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[{"artifact_id": "a-1", "collection_id": "c-1", "tf": 2, "dl": 6}],
        )
        unboosted = scorer.score_query([hit], stats_3_docs)[("a-1", "c-1")]
        boosted = scorer.score_query(
            [hit], stats_3_docs, field_boosts={"title": 5.0},
        )[("a-1", "c-1")]
        assert math.isclose(boosted, 5.0 * unboosted, rel_tol=1e-12)

    def test_unknown_field_uses_default_boost(self, stats_3_docs):
        # A hit on a field not in field_boosts → uses 1.0.
        token = "rare" * 16
        hit = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[{"artifact_id": "a-1", "collection_id": "c-1", "tf": 2, "dl": 6}],
        )
        with_boost = scorer.score_query(
            [hit], stats_3_docs, field_boosts={"description": 10.0},
        )[("a-1", "c-1")]
        without_boost = scorer.score_query([hit], stats_3_docs)[("a-1", "c-1")]
        # Title's boost defaulted to 1.0 in both cases.
        assert math.isclose(with_boost, without_boost, rel_tol=1e-12)

    def test_multi_field_aggregation(self, stats_3_docs):
        """The same artifact matches in title AND content — scores sum."""
        token_title = "rare" * 16
        token_content = "med" * 21 + "z"
        hits = [
            scorer.TokenHit(
                blind_token=token_title, field="title",
                entries=[
                    {"artifact_id": "a-1", "collection_id": "c-1", "tf": 1, "dl": 6}
                ],
            ),
            scorer.TokenHit(
                blind_token=token_content, field="content",
                entries=[
                    {"artifact_id": "a-1", "collection_id": "c-1", "tf": 4, "dl": 200}
                ],
            ),
        ]
        scores = scorer.score_query(hits, stats_3_docs)
        # Single (a-1, c-1) entry, score is the sum of two field contributions.
        title_contrib = scorer.bm25_term_score(
            tf=1, dl=6, df_value=1, doc_count=3, avg_dl=6.0,
        )
        content_contrib = scorer.bm25_term_score(
            tf=4, dl=200, df_value=2, doc_count=3, avg_dl=200.0,
        )
        assert math.isclose(
            scores[("a-1", "c-1")],
            title_contrib + content_contrib,
            rel_tol=1e-12,
        )

    def test_distinct_artifacts_scored_separately(self, stats_3_docs):
        token = "rare" * 16
        hit = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[
                {"artifact_id": "a-1", "collection_id": "c-1", "tf": 2, "dl": 6},
                {"artifact_id": "a-2", "collection_id": "c-1", "tf": 1, "dl": 12},
            ],
        )
        scores = scorer.score_query([hit], stats_3_docs)
        assert set(scores.keys()) == {("a-1", "c-1"), ("a-2", "c-1")}

    def test_same_artifact_multiple_collections_scored_separately(self, stats_3_docs):
        token = "rare" * 16
        hit = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[
                {"artifact_id": "a-1", "collection_id": "c-1", "tf": 2, "dl": 6},
                {"artifact_id": "a-1", "collection_id": "c-2", "tf": 3, "dl": 6},
            ],
        )
        scores = scorer.score_query([hit], stats_3_docs)
        assert set(scores.keys()) == {("a-1", "c-1"), ("a-1", "c-2")}

    def test_zero_df_short_circuits_posting_list(self, stats_3_docs):
        # A blind token with df=0 (e.g. fetched but the term was indexed
        # only on artifacts that have since been removed) → IDF=0 → no score.
        unknown_token = "z" * 64  # not in stats.df
        hit = scorer.TokenHit(
            blind_token=unknown_token, field="title",
            entries=[{"artifact_id": "a-1", "collection_id": "c-1", "tf": 5, "dl": 6}],
        )
        assert scorer.score_query([hit], stats_3_docs) == {}

    def test_zero_field_boost_short_circuits(self, stats_3_docs):
        token = "rare" * 16
        hit = scorer.TokenHit(
            blind_token=token, field="ignored",
            entries=[{"artifact_id": "a-1", "collection_id": "c-1", "tf": 2, "dl": 6}],
        )
        scores = scorer.score_query(
            [hit], stats_3_docs, field_boosts={"ignored": 0.0},
        )
        assert scores == {}

    def test_empty_entries_skipped(self, stats_3_docs):
        token = "rare" * 16
        hit = scorer.TokenHit(blind_token=token, field="title", entries=[])
        assert scorer.score_query([hit], stats_3_docs) == {}

    def test_malformed_entry_filtered(self, stats_3_docs):
        token = "rare" * 16
        hit = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[
                {"artifact_id": "a-1", "collection_id": "c-1", "tf": 2, "dl": 6},
                {"collection_id": "c-1", "tf": 1, "dl": 4},  # missing artifact_id
                {"artifact_id": "a-3", "tf": 1, "dl": 4},     # missing collection_id
                {"artifact_id": "a-4", "collection_id": "c-1", "tf": 0, "dl": 4},  # tf=0
                {"artifact_id": "a-5", "collection_id": "c-1"},  # missing tf
            ],
        )
        scores = scorer.score_query([hit], stats_3_docs)
        # Only the valid entry produced a score.
        assert list(scores.keys()) == [("a-1", "c-1")]


# ---------------------------------------------------------------------------
# Numerical sanity (rank-order properties)
# ---------------------------------------------------------------------------


class TestRankOrder:
    """Sanity checks on BM25's rank-order behavior — guards against silent
    formula regressions during refactoring."""

    def test_rare_term_outscores_common_term(self, stats_3_docs):
        # Two posting lists, both for the same artifact, identical tf+dl —
        # the rare term should produce a higher score than the common one.
        rare = scorer.TokenHit(
            blind_token="rare" * 16,  # df=1
            field="title",
            entries=[{"artifact_id": "a-1", "collection_id": "c-1", "tf": 2, "dl": 6}],
        )
        common = scorer.TokenHit(
            blind_token="common" * 10 + "abcd",  # df=3 (every doc)
            field="title",
            entries=[{"artifact_id": "a-1", "collection_id": "c-1", "tf": 2, "dl": 6}],
        )
        rare_score = scorer.score_query([rare], stats_3_docs)[("a-1", "c-1")]
        common_score = scorer.score_query([common], stats_3_docs)[("a-1", "c-1")]
        assert rare_score > common_score

    def test_shorter_doc_outscores_longer_for_same_tf(self, stats_3_docs):
        # Same artifact id used for both — but distinct entries. We want
        # the shorter doc to score higher with the same term frequency.
        token = "rare" * 16
        short = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[{"artifact_id": "a-short", "collection_id": "c-1", "tf": 2, "dl": 3}],
        )
        long_ = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[{"artifact_id": "a-long", "collection_id": "c-1", "tf": 2, "dl": 30}],
        )
        scores = scorer.score_query([short, long_], stats_3_docs)
        assert scores[("a-short", "c-1")] > scores[("a-long", "c-1")]

    def test_higher_tf_outscores_lower_tf(self, stats_3_docs):
        token = "rare" * 16
        low = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[{"artifact_id": "a-low", "collection_id": "c-1", "tf": 1, "dl": 6}],
        )
        high = scorer.TokenHit(
            blind_token=token, field="title",
            entries=[{"artifact_id": "a-high", "collection_id": "c-1", "tf": 5, "dl": 6}],
        )
        scores = scorer.score_query([low, high], stats_3_docs)
        assert scores[("a-high", "c-1")] > scores[("a-low", "c-1")]
