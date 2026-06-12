"""MantleSseSearchAccessor — SearchResult-shaped adapter (Step 2.6.9).

Bridges the MANTLE-SSE unified accessor (which returns ``UnifiedHit``)
into the ``search(SearchQuery) -> SearchResult`` contract the artifacts
router expects. After OpenSearch retirement (Step 2.6.9 part 2), this
is the canonical search backend — there's no legacy fallback.

Adapter responsibilities:

1. Parse the query (reuse :func:`parse_query`) so empty / corrected
   queries get the same metadata the prior accessor produced.
2. Resolve light-cone authorized contexts via
   :func:`resolve_authorized_contexts`.
3. Embed the query for the vector arm if an :class:`Embeddings` is
   wired. Embedding errors don't fail the search — the SSE arm survives.
4. Run the unified accessor's RRF fusion.
5. Hydrate each :class:`UnifiedHit` into a :class:`SearchHit` by reading
   the artifact's metadata from Arango (since neither index stores
   plaintext text).

See ``internal design notes`` § Query Flow.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional, Tuple

from kernel.embeddings import Embeddings

from ..lightcone import LightConeResolver
from .unified import MantleUnifiedAccessor, UnifiedHit

logger = logging.getLogger(__name__)


def resolve_authorized_contexts(
    arango_db,
    principal_id: str,
    *,
    lightcone: LightConeResolver,
    action: str = "read",
) -> List[Tuple[str, str]]:
    """Map the resolver's authorized artifact set into ``(cell_principal, collection)`` contexts.

    The light-cone resolver returns a flat set of artifact ids the
    requesting principal can ``read``. Each authorized artifact's
    ``collection_id`` is the MANTLE / SSE search scope; its **cell-key
    principal** is the collection's immutable origin root (NOT the
    artifact's ``created_by``) — the exact same value the index path used,
    so the derived keys match. We dedupe ``(cell_principal, collection)``.

    Returns an empty list when the principal has no authorized artifacts
    or when Arango lookups fail. Empty result is safe — both engines
    return no hits for empty contexts.

    Originally lived in `mantle.search.mantle.accessor` (the legacy
    OpenSearch+MANTLE fusion accessor); moved here when that module went
    away in Step 2.6.9 part 2.
    """
    from ..principal import resolve_cell_principal

    authorized = lightcone.resolve(principal_id, action=action)
    if not authorized:
        return []

    pairs: set[Tuple[str, str]] = set()
    principal_by_collection: dict[str, str] = {}
    art_collection = arango_db.collection("artifacts")
    for artifact_id in authorized:
        try:
            doc = art_collection.get(artifact_id)
        except Exception:  # noqa: BLE001 — Arango can raise broadly
            continue
        if not doc:
            continue
        collection_id = doc.get("collection_id") or doc.get("_key")
        if not collection_id:
            continue
        collection_id = str(collection_id)
        cell_principal = principal_by_collection.get(collection_id)
        if cell_principal is None:
            cell_principal = resolve_cell_principal(arango_db, collection_id)
            principal_by_collection[collection_id] = cell_principal
        if not cell_principal:
            continue
        pairs.add((cell_principal, collection_id))

    return sorted(pairs)


class MantleSseSearchAccessor:
    """Canonical router-shape search accessor (post-OpenSearch retirement).

    Returns the same :class:`SearchResult` shape as the legacy accessor
    so the router's response-mapping code is unaffected.
    """

    def __init__(
        self,
        unified: MantleUnifiedAccessor,
        lightcone: LightConeResolver,
        *,
        arango_db,
        embeddings: Optional[Embeddings] = None,
    ) -> None:
        self._unified = unified
        self._lightcone = lightcone
        self._arango_db = arango_db
        self._embeddings = embeddings or Embeddings()

    def search(self, query) -> "object":
        """Run SSE + MANTLE fused search, return a :class:`SearchResult`."""
        from search.query_parser import parse_query
        from search.types import SearchResult

        if self._arango_db is None:
            raise ValueError(
                "MantleSseSearchAccessor needs an arango_db for hydration"
            )

        parsed = parse_query(query.query_text)
        provided_embedding = getattr(query, "query_embedding", None)
        # Empty text is only a no-op when there's also no raw query vector;
        # an embedding-only query ("embedding activation") proceeds to kNN.
        if parsed.is_empty() and not provided_embedding:
            return SearchResult(
                hits=[],
                total=0,
                parsed_query=parsed,
                corrections=parsed.corrections,
                used_hybrid=False,
            )

        # Light-cone authorization — single ACL path post-2.6.9.
        contexts = resolve_authorized_contexts(
            self._arango_db,
            principal_id=query.user_id,
            lightcone=self._lightcone,
        )

        # Respect explicit scope from the router (body.scope → query.scope).
        # When scope is set, restrict to only the requested containers.
        # This is distinct from collection_ids (which carries the full authorized
        # set); scope is set only for user-explicit or principal-restricted searches.
        scope = getattr(query, "scope", None)
        if scope:
            allowed = set(scope)
            contexts = [(principal, col) for principal, col in contexts if col in allowed]

        logger.info(
            "MantleSseSearchAccessor: '%s' authorized to %d contexts",
            query.query_text, len(contexts),
        )

        if not contexts:
            return SearchResult(
                hits=[],
                total=0,
                parsed_query=parsed,
                corrections=parsed.corrections,
                used_hybrid=False,
            )

        # Vector arm: use a caller-provided query vector directly ("embedding
        # activation"), else embed the query text. Embedding errors degrade to
        # SSE-only — the lexical arm carries the search.
        embedding = (
            list(provided_embedding)
            if provided_embedding
            else self._embed_or_none(query.query_text, parsed)
        )

        # Wider top_k from each arm so RRF has rank diversity.
        unified_hits = self._unified.search(
            query.query_text,
            contexts,
            query_embedding=embedding,
            top_k=max(query.size * 3, 50),
        )

        if not unified_hits:
            return SearchResult(
                hits=[],
                total=0,
                parsed_query=parsed,
                corrections=parsed.corrections,
                used_hybrid=embedding is not None,
            )

        hits = self._hydrate(unified_hits[: query.size])
        return SearchResult(
            hits=hits,
            total=len(unified_hits),
            parsed_query=parsed,
            corrections=parsed.corrections,
            used_hybrid=embedding is not None,
        )

    def candidates(
        self,
        query,
        *,
        candidate_budget: int = 200,
        include_vectors: bool = False,
    ) -> dict:
        """Raw retrieval primitive — the single authorization chokepoint.

        Resolves the light-cone for ``query.user_id`` and returns ONLY the
        authorized candidate set (pre-hydration) with per-arm scores. Search
        *flavors* (the open standard one, or an external premium one like
        Beacon) rank within this set — they can never widen it, so MANTLE §1
        holds by construction. See ``internal design notes``.

        ``include_vectors`` is accepted for the premium re-rank path; candidate
        embeddings are not yet surfaced by the fusion layer, so vectors are
        omitted for now (TODO: thread candidate vectors through MantleQueryEngine
        → UnifiedHit).
        """
        from search.query_parser import parse_query

        if self._arango_db is None:
            raise ValueError("MantleSseSearchAccessor needs an arango_db")

        parsed = parse_query(query.query_text)
        provided_embedding = getattr(query, "query_embedding", None)
        if parsed.is_empty() and not provided_embedding:
            return {"candidates": [], "model_id": None}

        contexts = resolve_authorized_contexts(
            self._arango_db,
            principal_id=query.user_id,
            lightcone=self._lightcone,
        )
        scope = getattr(query, "scope", None)
        if scope:
            allowed = set(scope)
            contexts = [(p, c) for p, c in contexts if c in allowed]

        logger.info(
            "raw query: '%s' authorized to %d contexts (budget=%d)",
            query.query_text, len(contexts), candidate_budget,
        )
        if not contexts:
            return {"candidates": [], "model_id": None}

        embedding = (
            list(provided_embedding)
            if provided_embedding
            else self._embed_or_none(query.query_text, parsed)
        )
        budget = max(int(candidate_budget), 1)
        unified_hits = self._unified.search(
            query.query_text,
            contexts,
            query_embedding=embedding,
            top_k=budget,
        )

        out = []
        for h in unified_hits:
            rec = {
                "artifact_id": h.artifact_id,
                "collection_id": h.collection_id,
                "principal_id": h.principal_id,
                "sse_score": h.sse_score,
                "vector_score": h.vector_score,
                "rrf_score": h.rrf_score,
                "source": h.source,
            }
            if include_vectors:
                rec["vector"] = None  # TODO: surface candidate embeddings from the engine
            out.append(rec)
        return {"candidates": out, "model_id": getattr(self._unified, "model_id", None)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _embed_or_none(self, query_text: str, parsed) -> Optional[list[float]]:
        """Embed the query (or its semantic-flagged terms) for the vector arm.

        Returns ``None`` if embedding fails — the SSE-only path is still
        valid. Selects ~-flagged semantic terms when present (matching
        the prior accessor's behavior); falls back to the full query.
        """
        try:
            from search.query_parser import TermModifier
        except Exception:
            TermModifier = None  # type: ignore[assignment]

        text_for_embedding = query_text
        if TermModifier is not None:
            semantic_terms = [
                t.text for t in parsed.terms
                if getattr(t, "modifier", None) == TermModifier.SEMANTIC
            ]
            if semantic_terms:
                text_for_embedding = " ".join(semantic_terms)

        if not text_for_embedding.strip():
            return None
        try:
            results = self._embeddings([text_for_embedding])
            if not results:
                return None
            return results[0]
        except Exception:
            logger.exception("MantleSseSearchAccessor: embedding failed")
            return None

    def _hydrate(self, unified_hits: list[UnifiedHit]) -> list:
        """Read each artifact's metadata from Arango and produce SearchHits.

        Neither SSE nor MANTLE stores plaintext title / description /
        tags / content — those live in the ``artifacts`` collection.
        Hydration is one Arango ``get`` per fused hit. Failed lookups
        produce a SearchHit with empty metadata fields rather than
        dropping the hit entirely (the doc may have been removed
        between fusion and hydration).
        """
        from search.types import SearchHit

        art_collection = self._arango_db.collection("artifacts")
        out: list = []
        for hit in unified_hits:
            doc = self._safe_get(art_collection, hit.artifact_id)
            ctx = self._parse_context(doc)
            tags_raw = ctx.get("tags") or ctx.get("tags_canonical") or []
            tags = (
                [str(t) for t in tags_raw if str(t).strip()]
                if isinstance(tags_raw, list)
                else []
            )
            out.append(
                SearchHit(
                    doc_id=hit.artifact_id,
                    score=hit.rrf_score,
                    root_id=(
                        (doc or {}).get("root_id")
                        or hit.artifact_id
                    ),
                    version_id=(
                        (doc or {}).get("_key")
                        or hit.artifact_id
                    ),
                    title=str(ctx.get("title") or ctx.get("name") or ""),
                    description=str(ctx.get("description") or ""),
                    content=str((doc or {}).get("content") or ""),
                    tags=tags,
                    metadata={
                        "sse_score": hit.sse_score,
                        "vector_score": hit.vector_score,
                        "source": hit.source,
                    },
                    collection_id=hit.collection_id,
                    principal_id=hit.principal_id,
                    state=(doc or {}).get("state"),
                    is_head=None,
                    highlights=None,
                )
            )
        return out

    @staticmethod
    def _safe_get(art_collection, artifact_id: str):
        try:
            return art_collection.get(artifact_id)
        except Exception:  # noqa: BLE001 — Arango raises broadly
            return None

    @staticmethod
    def _parse_context(doc) -> dict:
        if not doc:
            return {}
        ctx = doc.get("context")
        if not ctx:
            return {}
        if isinstance(ctx, dict):
            return ctx
        if isinstance(ctx, str):
            try:
                parsed = json.loads(ctx)
            except (TypeError, ValueError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}


__all__ = ["MantleSseSearchAccessor", "resolve_authorized_contexts"]
