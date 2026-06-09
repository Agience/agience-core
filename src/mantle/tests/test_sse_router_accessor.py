"""Tests for `search.mantle.sse.router_accessor.MantleSseSearchAccessor`
(MANTLE-SSE Step 2.6.9 router integration).

Covers:

- search(SearchQuery) returns SearchResult with the legacy shape.
- Empty query → empty SearchResult with parsed metadata.
- Light-cone with no authorized contexts → empty SearchResult.
- Hydration: artifact metadata (title/description/tags/state) read from
  Arango docs; missing docs degrade to empty fields rather than dropping.
- Embedding failure: vector arm dies, SSE-only path still produces hits.
- Embedding absent (no semantic terms): used_hybrid=False.
- Trim to query.size; total = pre-trim count.
- arango_db=None raises ValueError (constructor contract).
"""

from __future__ import annotations

import json
from typing import Optional

import pytest

from search.mantle.sse.router_accessor import MantleSseSearchAccessor
from search.mantle.sse.unified import UnifiedHit


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeArtifactCollection:
    def __init__(self, docs: dict[str, dict]) -> None:
        self._docs = docs

    def get(self, artifact_id: str) -> Optional[dict]:
        return self._docs.get(artifact_id)


class _FakeArangoDB:
    def __init__(self, docs: Optional[dict[str, dict]] = None) -> None:
        self._artifacts = _FakeArtifactCollection(docs or {})

    def collection(self, name: str) -> _FakeArtifactCollection:
        if name == "artifacts":
            return self._artifacts
        raise ValueError(f"unknown collection {name!r}")


class _FakeLightCone:
    def __init__(self, authorized: Optional[list[str]] = None) -> None:
        self._authorized = authorized or []

    def resolve(self, principal_id: str, *, action: str = "read") -> set[str]:
        return set(self._authorized)


class _FakeUnified:
    """Stand-in for MantleUnifiedAccessor — records inputs and returns
    a canned hit list."""

    def __init__(self, hits: Optional[list[UnifiedHit]] = None) -> None:
        self.calls: list[dict] = []
        self._hits = hits or []

    def search(self, query_text, contexts, *, query_embedding, top_k, **kwargs):
        self.calls.append({
            "query_text": query_text,
            "contexts": list(contexts),
            "query_embedding": query_embedding,
            "top_k": top_k,
        })
        return list(self._hits)


class _FakeEmbeddings:
    """Returns a deterministic embedding (or raises if requested)."""

    def __init__(self, *, raise_on_call: bool = False) -> None:
        self.raise_on_call = raise_on_call
        self.calls: list[list[str]] = []

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.raise_on_call:
            raise RuntimeError("embedder down")
        return [[0.1, 0.2, 0.3] for _ in texts]


def _make_query(
    query_text: str = "alpha", *,
    user_id: str = "user-1", size: int = 20,
):
    """Build a SearchQuery with the legacy fields the router constructs.

    Imported lazily so the test module can be collected even if
    accessor.search_accessor's dependency tree is heavy."""
    from search.types import SearchQuery
    return SearchQuery(
        query_text=query_text,
        user_id=user_id,
        size=size,
    )


def _make_artifact_doc(artifact_id, *, title="", description="", tags=None,
                      content="", state="committed") -> dict:
    return {
        "_key": artifact_id,
        "root_id": artifact_id,
        "context": json.dumps({
            "title": title,
            "description": description,
            "tags": tags or [],
        }),
        "content": content,
        "state": state,
        "created_by": "user-1",
        "principal_id": "user-1",
    }


def _make_unified_hit(
    artifact_id, score=0.9, *,
    collection_id="col-1", principal_id="user-1",
    sse_score: Optional[float] = None,
    vector_score: Optional[float] = None,
    source: str = "sse",
) -> UnifiedHit:
    return UnifiedHit(
        artifact_id=artifact_id,
        collection_id=collection_id,
        principal_id=principal_id,
        rrf_score=score,
        sse_score=sse_score if sse_score is not None else (
            score if source in ("sse", "both") else None
        ),
        vector_score=vector_score if vector_score is not None else (
            score if source in ("vector", "both") else None
        ),
        source=source,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchEmptyShortCircuits:
    def test_empty_query_returns_empty_result(self):
        unified = _FakeUnified()
        lightcone = _FakeLightCone()
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(),
            embeddings=_FakeEmbeddings(),
        )
        from search.types import SearchResult
        result = acc.search(_make_query(""))
        assert isinstance(result, SearchResult)
        assert result.hits == []
        assert result.total == 0
        # Unified engine should NOT be invoked.
        assert unified.calls == []

    def test_no_authorized_contexts_returns_empty(self):
        unified = _FakeUnified(hits=[_make_unified_hit("art-1")])
        lightcone = _FakeLightCone()  # no authorized artifacts
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(),
            embeddings=_FakeEmbeddings(),
        )
        result = acc.search(_make_query("alpha"))
        assert result.hits == []
        # Unified engine still not invoked — short-circuit before fanout.
        assert unified.calls == []

    def test_arango_db_none_raises(self):
        unified = _FakeUnified()
        lightcone = _FakeLightCone()
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=None,
            embeddings=_FakeEmbeddings(),
        )
        with pytest.raises(ValueError, match="arango_db"):
            acc.search(_make_query("alpha"))


class TestHydration:
    def test_hydrates_from_artifact_doc(self):
        # Light-cone authorizes art-1 in col-1; unified returns one hit.
        docs = {"art-1": _make_artifact_doc(
            "art-1",
            title="Encryption Library",
            description="A MANTLE-SSE module",
            tags=["search", "encrypted"],
            content="some content text",
            state="committed",
        )}
        # Authorize art-1 — light-cone returns it; resolve_authorized_contexts
        # then maps to (owner, collection_id) which is read from the doc.
        unified = _FakeUnified(hits=[_make_unified_hit("art-1")])
        lightcone = _FakeLightCone(authorized=["art-1"])
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(),
        )
        result = acc.search(_make_query("encryption"))
        assert len(result.hits) == 1
        hit = result.hits[0]
        assert hit.doc_id == "art-1"
        assert hit.title == "Encryption Library"
        assert hit.description == "A MANTLE-SSE module"
        assert hit.tags == ["search", "encrypted"]
        assert hit.content == "some content text"
        assert hit.state == "committed"
        # Underlying scores travel in metadata.
        assert hit.metadata["source"] == "sse"
        assert hit.metadata["sse_score"] is not None

    def test_missing_doc_yields_empty_metadata(self):
        # Fused hit references an artifact that's been deleted between
        # fusion and hydration — return a SearchHit with empty fields.
        unified = _FakeUnified(hits=[_make_unified_hit("art-gone")])
        lightcone = _FakeLightCone(authorized=["art-1"])
        # docs has art-1 (so contexts can be resolved) but not art-gone.
        docs = {"art-1": _make_artifact_doc("art-1")}
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(),
        )
        result = acc.search(_make_query("alpha"))
        assert len(result.hits) == 1
        # Title/description empty; doc_id still the unified-hit id.
        assert result.hits[0].doc_id == "art-gone"
        assert result.hits[0].title == ""
        assert result.hits[0].description == ""

    def test_malformed_context_falls_back_to_empty(self):
        # context isn't valid JSON.
        docs = {"art-1": {
            "_key": "art-1",
            "root_id": "art-1",
            "context": "{not json",
            "content": "",
            "state": "committed",
            "created_by": "user-1",
            "principal_id": "user-1",
        }}
        unified = _FakeUnified(hits=[_make_unified_hit("art-1")])
        lightcone = _FakeLightCone(authorized=["art-1"])
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(),
        )
        result = acc.search(_make_query("alpha"))
        assert result.hits[0].title == ""
        assert result.hits[0].tags == []


class TestEmbedding:
    def test_embedding_failure_falls_back_to_sse_only(self):
        docs = {"art-1": _make_artifact_doc("art-1")}
        unified = _FakeUnified(hits=[_make_unified_hit("art-1")])
        lightcone = _FakeLightCone(authorized=["art-1"])
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(raise_on_call=True),
        )
        result = acc.search(_make_query("alpha"))
        # SSE arm still produced a hit.
        assert len(result.hits) == 1
        # used_hybrid=False because vector arm wasn't engaged.
        assert result.used_hybrid is False
        # Unified engine called with query_embedding=None.
        assert unified.calls[0]["query_embedding"] is None

    def test_used_hybrid_true_when_embedding_succeeds(self):
        docs = {"art-1": _make_artifact_doc("art-1")}
        unified = _FakeUnified(hits=[_make_unified_hit("art-1")])
        lightcone = _FakeLightCone(authorized=["art-1"])
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(),
        )
        result = acc.search(_make_query("alpha"))
        assert result.used_hybrid is True
        # Embedding made it to the unified engine.
        assert unified.calls[0]["query_embedding"] == [0.1, 0.2, 0.3]


class TestSizeAndTotal:
    def test_trims_to_query_size(self):
        # Unified returns 5 hits; query.size=2.
        hits = [_make_unified_hit(f"art-{i}", score=1.0 - 0.01 * i)
                for i in range(5)]
        docs = {f"art-{i}": _make_artifact_doc(f"art-{i}") for i in range(5)}
        unified = _FakeUnified(hits=hits)
        lightcone = _FakeLightCone(authorized=["art-0"])
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(),
        )
        result = acc.search(_make_query("alpha", size=2))
        assert len(result.hits) == 2
        # total reflects pre-trim count.
        assert result.total == 5

    def test_no_hits_from_unified(self):
        docs = {"art-1": _make_artifact_doc("art-1")}
        unified = _FakeUnified(hits=[])
        lightcone = _FakeLightCone(authorized=["art-1"])
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(),
        )
        result = acc.search(_make_query("alpha"))
        assert result.hits == []
        assert result.total == 0


class TestScopeFiltering:
    """query.scope restricts search to explicit container IDs."""

    def _make_docs_two_collections(self):
        # art-A lives in col-A; art-B lives in col-B.
        return {
            "art-A": {
                "_key": "art-A", "root_id": "art-A",
                "context": '{"title": "Alpha Article"}',
                "content": "", "state": "committed",
                "created_by": "user-1", "principal_id": "user-1",
                "collection_id": "col-A",
            },
            "art-B": {
                "_key": "art-B", "root_id": "art-B",
                "context": '{"title": "Beta Article"}',
                "content": "", "state": "committed",
                "created_by": "user-1", "principal_id": "user-1",
                "collection_id": "col-B",
            },
        }

    def test_scope_restricts_to_matching_collection(self):
        # Light-cone authorizes both art-A and art-B.
        # query.scope = ["col-A"] → only contexts in col-A should be searched.
        docs = self._make_docs_two_collections()
        unified = _FakeUnified(hits=[_make_unified_hit("art-A", collection_id="col-A")])
        lightcone = _FakeLightCone(authorized=["art-A", "art-B"])
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(),
        )
        from search.types import SearchQuery
        query = SearchQuery(
            query_text="alpha",
            user_id="user-1",
            scope=["col-A"],
            size=20,
        )
        acc.search(query)
        # Unified engine should have been called with only col-A context.
        assert unified.calls, "unified.search should have been invoked"
        call_contexts = unified.calls[0]["contexts"]
        assert all(col == "col-A" for _, col in call_contexts), (
            f"Expected only col-A contexts, got {call_contexts}"
        )

    def test_scope_none_searches_all_contexts(self):
        # No explicit scope → all contexts from the light-cone are used.
        docs = self._make_docs_two_collections()
        unified = _FakeUnified(hits=[])
        lightcone = _FakeLightCone(authorized=["art-A", "art-B"])
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(),
        )
        from search.types import SearchQuery
        query = SearchQuery(query_text="alpha", user_id="user-1", scope=None, size=20)
        acc.search(query)
        call_contexts = unified.calls[0]["contexts"]
        collection_ids_searched = {col for _, col in call_contexts}
        assert "col-A" in collection_ids_searched
        assert "col-B" in collection_ids_searched

    def test_scope_no_match_returns_empty(self):
        # scope points at a collection that is not in any authorized context.
        docs = self._make_docs_two_collections()
        unified = _FakeUnified(hits=[_make_unified_hit("art-A", collection_id="col-A")])
        lightcone = _FakeLightCone(authorized=["art-A", "art-B"])
        acc = MantleSseSearchAccessor(
            unified, lightcone,
            arango_db=_FakeArangoDB(docs),
            embeddings=_FakeEmbeddings(),
        )
        from search.types import SearchQuery
        query = SearchQuery(
            query_text="alpha",
            user_id="user-1",
            scope=["col-UNKNOWN"],
            size=20,
        )
        result = acc.search(query)
        assert result.hits == []
        assert result.total == 0
        # Unified engine must NOT have been called — short-circuit on empty contexts.
        assert unified.calls == []

