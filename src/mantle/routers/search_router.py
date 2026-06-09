"""Raw search query primitive — the authorization chokepoint for flavored search.

`POST /search/query` resolves the light-cone for the calling user and returns the
**authorized candidate set** (per-arm scores, optionally vectors). It does no
flavored ranking. Search *flavors* — the open standard one, or an external
premium one like Beacon — call this and rank within the returned set; they can
never widen access (MANTLE §1 holds by construction).

This is additive: the legacy `POST /artifacts/search` is unchanged. See
`.dev/features/search-as-artifact.md`.
"""

from typing import List, Optional

from arango.database import StandardDatabase
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.dependencies import AuthContext, get_arango_db, get_auth

search_router = APIRouter(prefix="/search", tags=["Search"])


class RawQueryRequest(BaseModel):
    query_text: Optional[str] = None
    embedding: Optional[List[float]] = None      # raw query vector (XOR query_text)
    scope: Optional[List[str]] = None            # restrict to these container IDs
    candidate_budget: int = 200                  # how many candidates to retrieve for ranking
    include_vectors: bool = False                # reserved for vector-level premium re-rank


@search_router.post("/query")
async def raw_query(
    body: RawQueryRequest,
    auth: AuthContext = Depends(get_auth),
    arango_db: StandardDatabase = Depends(get_arango_db),
):
    """Return the authorized candidate set for a query. Auth = the calling user;
    candidates are filtered to that user's light-cone inside the accessor."""
    user_id = auth.user_id
    if not user_id and not auth.bearer_grant:
        raise HTTPException(status_code=401, detail="Missing authorization")

    has_text = bool(body.query_text and body.query_text.strip())
    has_embedding = bool(body.embedding)
    if has_text == has_embedding:
        raise HTTPException(
            status_code=400,
            detail="provide exactly one of 'query_text' or 'embedding'",
        )

    from search.types import SearchQuery
    from search.mantle.wiring import build_sse_search_accessor

    query = SearchQuery(
        query_text=body.query_text or "",
        query_embedding=body.embedding,
        user_id=user_id or "",
        scope=body.scope,
        use_hybrid=None,
        aperture=0.75,
        from_=0,
        size=body.candidate_budget,
        sort="relevance",
        highlight=False,
    )

    accessor = build_sse_search_accessor(arango_db)
    if accessor is None:
        raise HTTPException(
            status_code=503,
            detail="Encrypted search is not available (Oracle / S3 / Arango prerequisite missing)",
        )

    try:
        return accessor.candidates(
            query,
            candidate_budget=body.candidate_budget,
            include_vectors=body.include_vectors,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}")
