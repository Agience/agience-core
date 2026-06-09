"""MantleSseSearchAccessor.candidates() — the raw retrieval primitive.

candidates() shares search()'s light-cone chokepoint but returns pre-hydration
candidates (per-arm scores) instead of a hydrated SearchResult. Context
resolution is patched (covered by the search() tests); this isolates candidates'
own shaping + the include_vectors switch.
"""

from unittest.mock import patch

from search.mantle.sse.router_accessor import MantleSseSearchAccessor
from search.mantle.sse.unified import UnifiedHit

_RESOLVE = "search.mantle.sse.router_accessor.resolve_authorized_contexts"


class _FakeUnified:
    def __init__(self, hits):
        self._hits = hits

    def search(self, query_text, contexts, *, query_embedding, top_k, **kw):
        return list(self._hits)


class _FakeEmbeddings:
    def __call__(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def _hit(aid):
    return UnifiedHit(
        artifact_id=aid, collection_id="c1", principal_id="p1",
        rrf_score=0.02, sse_score=0.1, vector_score=0.9, source="both",
    )


def _query(text="alpha"):
    from search.types import SearchQuery
    return SearchQuery(query_text=text, user_id="u1", size=20)


def _accessor(hits):
    return MantleSseSearchAccessor(
        _FakeUnified(hits), object(), arango_db=object(), embeddings=_FakeEmbeddings(),
    )


def test_candidates_returns_scored_candidates_over_authorized_contexts():
    acc = _accessor([_hit("a1"), _hit("a2")])
    with patch(_RESOLVE, return_value=[("p1", "c1")]):
        out = acc.candidates(_query(), candidate_budget=50)
    assert [c["artifact_id"] for c in out["candidates"]] == ["a1", "a2"]
    assert out["candidates"][0]["vector_score"] == 0.9
    assert "vector" not in out["candidates"][0]  # include_vectors defaults False


def test_candidates_include_vectors_adds_reserved_placeholder():
    acc = _accessor([_hit("a1")])
    with patch(_RESOLVE, return_value=[("p1", "c1")]):
        out = acc.candidates(_query(), include_vectors=True)
    assert out["candidates"][0]["vector"] is None  # reserved until the engine surfaces vectors


def test_candidates_empty_when_no_authorized_contexts():
    acc = _accessor([_hit("a1")])
    with patch(_RESOLVE, return_value=[]):
        out = acc.candidates(_query())
    assert out["candidates"] == []
