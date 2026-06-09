"""Router tests for POST /search/query — the raw query primitive (auth chokepoint).

The encrypted-search backend is mocked at the accessor seam (tests never touch a
real Oracle/S3/Arango); these assert the HTTP contract + validation + the 503
no-fallback behavior.
"""

from unittest.mock import MagicMock, patch

import pytest

_CANDIDATES = {
    "candidates": [
        {"artifact_id": "a1", "collection_id": "c1", "principal_id": "p1",
         "sse_score": 0.1, "vector_score": 0.9, "rrf_score": 0.02, "source": "both"},
    ],
    "model_id": "hf:BAAI/bge-m3@1.0",
}


@pytest.mark.asyncio
async def test_query_returns_authorized_candidates(client):
    accessor = MagicMock()
    accessor.candidates.return_value = _CANDIDATES
    with patch("search.mantle.wiring.build_sse_search_accessor", return_value=accessor):
        resp = await client.post("/search/query", json={"query_text": "hello", "candidate_budget": 50})
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] == "hf:BAAI/bge-m3@1.0"
    assert body["candidates"][0]["artifact_id"] == "a1"
    assert accessor.candidates.called  # the auth chokepoint was exercised


@pytest.mark.asyncio
async def test_query_rejects_both_text_and_embedding(client):
    resp = await client.post("/search/query", json={"query_text": "hi", "embedding": [0.1, 0.2]})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_query_rejects_neither_text_nor_embedding(client):
    resp = await client.post("/search/query", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_query_503_when_search_backend_unavailable(client):
    # No plaintext fallback by design — missing Oracle/S3/Arango → 503.
    with patch("search.mantle.wiring.build_sse_search_accessor", return_value=None):
        resp = await client.post("/search/query", json={"query_text": "hi"})
    assert resp.status_code == 503
