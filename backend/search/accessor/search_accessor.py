"""
Search Accessor v3.1 - Unified Global Search

Key features:
- Single unified /search endpoint (no separate workspace/collection)
- Uses query_parser and query_builder
- Hybrid is opt-in (via ~ terms or @hybrid:on)
- Natural language default
- owner_id ACL (no tenant_id)
"""

import logging
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass

from core.embeddings import Embeddings
from db.opensearch import search, knn_search
from search.query_parser import parse_query, ParsedQuery, TermModifier
from search.query_builder import QueryBuilder

logger = logging.getLogger(__name__)

# Embedding function singleton
_embeddings = Embeddings()


@dataclass
class SearchQuery:
    """Unified search query parameters."""
    
    query_text: str
    user_id: str
    
    # Scope filters (optional - for filtering results)
    collection_ids: Optional[List[str]] = None
    grant_keys: Optional[List[str]] = None
    
    # Pagination
    from_: int = 0
    size: int = 20
    
    # Search mode (auto-determined by hybrid trigger if not specified)
    use_hybrid: Optional[bool] = None  # None = auto-detect
    
    # Sorting
    sort: Optional[Literal["relevance", "recency"]] = "relevance"
    
    # UI features
    highlight: bool = False
    aperture: float = 0.75  # Relevance threshold: 0.0 (strict/closed) to 1.0 (permissive/wide neighborhood)
    
    # Control parameters from @ namespace
    controls: Optional[Dict[str, str]] = None


@dataclass
class SearchHit:
    """Single search result hit."""
    
    doc_id: str
    score: float
    root_id: str
    version_id: str
    
    # Content
    title: str
    description: str
    content: str
    tags: List[str]
    metadata: Dict[str, Any]
    
    # Context fields
    collection_id: Optional[str] = None
    owner_id: Optional[str] = None
    state: Optional[str] = None
    is_head: Optional[bool] = None
    
    # Highlighting
    highlights: Optional[Dict[str, List[str]]] = None


@dataclass
class SearchResult:
    """Search result with hits, facets, and metadata."""
    
    hits: List[SearchHit]
    total: int
    
    # Query metadata
    parsed_query: ParsedQuery
    corrections: List[str]
    used_hybrid: bool
    
    # Facets (optional)
    facets: Optional[Dict[str, List[Dict[str, Any]]]] = None


class SearchAccessor:
    """
    Unified search accessor using v3.1 parser and builder.
    """
    
    # Canonical artifact search index (single index for BM25 + kNN)
    ARTIFACTS_INDEX = "artifacts"
    
    def __init__(self):
        self.query_builder = QueryBuilder()
        self.embeddings = _embeddings
    
    def search(self, query: SearchQuery) -> SearchResult:
        """
        Execute unified search across all artifacts.
        
        Args:
            query: SearchQuery with query text and filters
            
        Returns:
            SearchResult with hits and metadata
        """
        logger.info(f"Search query: '{query.query_text}' user_id={query.user_id} collection_ids={query.collection_ids}")
        
        # Parse query
        parsed = parse_query(query.query_text)
        
        # Handle empty queries
        if parsed.is_empty():
            return SearchResult(
                hits=[],
                total=0,
                parsed_query=parsed,
                corrections=parsed.corrections,
                used_hybrid=False
            )
        
        # Determine if hybrid search should be used
        use_hybrid = self.should_use_hybrid(query, parsed)
        
        # Build base filter from pre-computed collection_ids (populated by the caller).
        _should: List[Dict[str, Any]] = []
        if query.user_id:
            _should.append({"term": {"owner_id": query.user_id}})
        if query.collection_ids:
            _should.append({"terms": {"collection_id": query.collection_ids}})
        base_filter: Dict[str, Any] = (
            {"bool": {"must": [{"bool": {"should": _should, "minimum_should_match": 1}}]}}
            if _should else {"bool": {"must": [{"match_none": {}}]}}
        )
        logger.info(f"'{query.query_text}' - ACL filter: {base_filter}")
        
        # Execute search (statistical filtering applied within hybrid search)
        if use_hybrid:
            logger.info(f"Using hybrid search (BM25 + kNN) for: '{query.query_text}'")
            hits, total = self._execute_hybrid_search(query, parsed, base_filter)
        else:
            logger.info(f"Using BM25-only search for: '{query.query_text}'")
            hits, total = self._execute_bm25_search(query, parsed, base_filter)
        
        # Debug: log hits before conversion
        logger.info(f"'{query.query_text}' - Converting {len(hits)} hits, total={total}")
        if hits:
            logger.info(f"'{query.query_text}' - First hit: id={hits[0].get('id')}, score={hits[0].get('score')}, root_id={hits[0].get('source', {}).get('root_id')}")
        
        # Convert to SearchHit and apply final size limit
        search_hits = [self._to_search_hit(h) for h in hits[:query.size]]
        
        logger.info(f"'{query.query_text}' - Returning {len(search_hits)} search hits")
        
        return SearchResult(
            hits=search_hits,
            total=total,
            parsed_query=parsed,
            corrections=parsed.corrections,
            used_hybrid=use_hybrid
        )
    
    def should_use_hybrid(self, query: SearchQuery, parsed: ParsedQuery) -> bool:
        """
        Determine if hybrid (BM25 + kNN) search should be used.
        
        Default: BM25 only (industry standard - fast, predictable)
        
        Priority:
        1. Explicit @hybrid:on/off control
        2. Query parameter use_hybrid
        3. Presence of semantic (~) terms enables hybrid
        4. Modifier-aware: Don't use semantic when strict operators dominate
           - If query has ONLY filters (no text terms), disable hybrid
           - If query has required terms (+) but no semantic terms, disable hybrid
        5. Default: BM25 only
        """
        # Check explicit control
        if parsed.controls.get("hybrid") == "off":
            return False
        if parsed.controls.get("hybrid") == "on":
            return True
        
        # Check query parameter
        if query.use_hybrid is not None:
            return query.use_hybrid
        
        # Check if any term has semantic modifier (~)
        # If user explicitly requests semantic search, enable hybrid
        has_semantic_terms = any(t.modifier == TermModifier.SEMANTIC for t in parsed.terms)
        if has_semantic_terms:
            return True
        
        # Modifier-aware: Don't pollute strict queries with semantic expansion
        # If query is filters-only (no text terms), disable hybrid
        if not parsed.terms:
            logger.info(f"'{query.query_text}' - Filters-only query, disabling hybrid")
            return False
        
        # If ALL terms are required (+) and none are semantic (~), disable hybrid
        # This prevents semantic pollution of strict AND queries like "+budget +q1 +2025"
        all_required = all(t.modifier == TermModifier.REQUIRED for t in parsed.terms)
        if all_required and not has_semantic_terms:
            logger.info(f"'{query.query_text}' - All required terms (+), no semantic (~), disabling hybrid")
            return False
        
        # Default: BM25 only (no automatic hybrid)
        return False
    
    def _execute_bm25_search(
        self,
        query: SearchQuery,
        parsed: ParsedQuery,
        base_filter: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], int]:
        """Execute BM25-only search"""
        # Build OpenSearch query
        opensearch_query = self.query_builder.build_bm25_query(parsed, base_filter)
        
        # Add highlighting if requested
        highlight = None
        if query.highlight:
            highlight = {
                "fields": {
                    "title": {},
                    "description": {},
                    "content": {},
                },
                "fragment_size": 150,
                "number_of_fragments": 2,
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"]
            }
        
        # Dynamic BM25 size based on requested size (fetch 2x for better ranking)
        # Clamp for performance
        bm25_size = min(max(query.size * 2, 20), 500)
        
        # Execute BM25 on the canonical retrieval index.
        # All searchable artifacts must be represented in artifacts.
        result = search(
            self.ARTIFACTS_INDEX,
            opensearch_query,
            size=bm25_size,
            from_=query.from_,
            sort=None,  # Always relevance for BM25
            highlight=highlight
        )

        hits = []
        for hit in result.get("hits", {}).get("hits", []):
            hits.append(
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "source": hit["_source"],
                    "highlight": hit.get("highlight"),
                }
            )

        total = result.get("hits", {}).get("total", {}).get("value", 0)

        logger.info("'%s' - BM25 search returned %d hits (total: %d)", query.query_text, len(hits), total)
        return hits, total
    
    def _execute_hybrid_search(
        self,
        query: SearchQuery,
        parsed: ParsedQuery,
        base_filter: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Execute hybrid BM25 + kNN search with RRF fusion.
        
        Strategy:
        1. BM25 search: ALL terms (lexical matching with stemming)
           - Non-semantic terms (e.g., 'grocery') -> lexical match
           - Semantic terms (e.g., '~store') -> ALSO lexical match in BM25
        2. kNN search: ONLY semantic terms embedded
           - Extract terms with ~ modifier
           - Embed only those terms for semantic similarity
        3. RRF fusion: Combine and re-rank
           - Docs in BOTH lists rank highest
           - Docs in one list rank lower
        
        Example: 'grocery ~store'
        - BM25: matches "grocery" OR "store" (lexical)
        - kNN: embeds "store" -> matches "shop", "market" (semantic)
        - Combined: "grocery store" ranks highest (appears in both)
        
        Example: '~"grocery store"'
        - BM25: matches "grocery" OR "store" (lexical, phrase broken up)
        - kNN: embeds "grocery store" -> matches "supermarket" (semantic)
        - Combined: hybrid results from both lexical and semantic
        
        Aperture only affects kNN (semantic) results, NOT BM25 (lexical) results.
        """
        # BM25 search - ALL terms (lexical + semantic terms treated as lexical)
        bm25_size = min(max(query.size * 3, 20), 500)
        
        opensearch_query = self.query_builder.build_bm25_query(parsed, base_filter)
        
        bm25_result = search(
            self.ARTIFACTS_INDEX,
            opensearch_query,
            size=bm25_size,
            from_=0  # Always fetch from beginning for fusion
        )
        
        bm25_hits = []
        for hit in bm25_result.get("hits", {}).get("hits", []):
            bm25_hits.append({
                "id": hit["_id"],
                "score": hit["_score"],
                "source": hit["_source"]
            })
        
        # kNN search - embed ONLY semantic terms (terms with ~ modifier)
        # Extract semantic terms and join them for embedding
        semantic_terms = [t.text for t in parsed.terms if t.modifier == TermModifier.SEMANTIC]
        semantic_query = " ".join(semantic_terms)
        
        logger.info(f"'{query.query_text}' - Semantic terms: '{semantic_query}'")
        
        query_vector = self.embeddings([semantic_query])[0]
        
        # Dynamic K based on requested size (fetch 3x for fusion buffer)
        # Clamp between reasonable bounds for performance
        knn_k = min(max(query.size * 3, 20), 200)
        knn_candidates = min(knn_k * 5, 1000)  # 5x multiplier for good recall
        
        logger.info(f"'{query.query_text}' - Fetching BM25={bm25_size}, kNN k={knn_k}, candidates={knn_candidates}")
        
        knn_result = knn_search(
            self.ARTIFACTS_INDEX,
            field="content_vector",
            query_vector=query_vector,
            k=knn_k,
            num_candidates=knn_candidates,
            filter_query=base_filter
        )
        
        # Convert kNN hits
        raw_knn_hits = []
        for hit in knn_result.get("hits", {}).get("hits", []):
            raw_knn_hits.append({
                "id": hit["_id"],
                "score": hit["_score"],
                "source": hit["_source"]
            })
        
        # Apply aperture filtering to kNN results ONLY (controls semantic neighborhood)
        # BM25 results are NOT filtered - we trust BM25 relevance scoring
        filtered_knn_hits = self._apply_aperture_filter(
            raw_knn_hits,
            aperture=query.aperture,
            query_text=query.query_text
        )
        
        # Reciprocal Rank Fusion combines both result sets (deduplicates by ID)
        # Documents appearing in BOTH lists get highest combined scores
        # Example: "grocery store" appears in both BM25 and kNN -> TOP RANK
        fused_hits = self._reciprocal_rank_fusion(bm25_hits, filtered_knn_hits)
        
        # Total is max of both
        total = max(
            bm25_result.get("hits", {}).get("total", {}).get("value", 0),
            knn_result.get("hits", {}).get("total", {}).get("value", 0)
        )
        
        logger.info(
            f"'{query.query_text}' - Hybrid search: BM25={len(bm25_hits)}, "
            f"kNN={len(raw_knn_hits)}->{len(filtered_knn_hits)} (aperture={query.aperture}), "
            f"fused={len(fused_hits)}, total={total}"
        )
        
        return fused_hits, total
    
    def _reciprocal_rank_fusion(
        self,
        bm25_hits: List[Dict[str, Any]],
        knn_hits: List[Dict[str, Any]],
        k: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Combine BM25 and kNN results using Reciprocal Rank Fusion.
        
        RRF score = sum(1 / (k + rank)) for each list where doc appears.
        """
        scores = {}
        sources = {}
        
        # Process BM25 hits
        for rank, hit in enumerate(bm25_hits, start=1):
            doc_id = hit["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
            sources[doc_id] = hit["source"]
        
        # Process kNN hits
        for rank, hit in enumerate(knn_hits, start=1):
            doc_id = hit["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
            sources[doc_id] = hit["source"]
        
        # Sort by combined score
        fused = [
            {"id": doc_id, "score": score, "source": sources[doc_id]}
            for doc_id, score in scores.items()
        ]
        fused.sort(key=lambda x: x["score"], reverse=True)
        
        return fused
    
    def _apply_aperture_filter(
        self,
        hits: List[Dict[str, Any]],
        aperture: float,
        query_text: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Apply aperture-based filtering to kNN (semantic) search results.
        
        Operates on kNN cosine similarity scores (0.0-1.0 range, higher = more similar).
        Used ONLY for semantic search - BM25 results are never filtered.
        
        Process:
        1. Calculate score statistics (mean, stdev)
        2. Find elbow point (biggest score drop)
        3. Set threshold based on aperture:
           - aperture=0.0: very strict (only top results, small neighborhood)
           - aperture=0.5: at elbow (balanced, natural grouping)
           - aperture=1.0: very permissive (large neighborhood, many results)
        
        Args:
            hits: kNN results with cosine similarity scores (0.0-1.0)
            aperture: User-controlled threshold (0.0=strict, 1.0=permissive)
            query_text: For logging
        """
        if len(hits) <= 3:
            return hits  # Too few to analyze
        
        scores = [h["score"] for h in hits]
        
        # Statistical analysis
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        stdev = variance ** 0.5
        
        # Find elbow (biggest score drop)
        score_drops = []
        for i in range(len(scores) - 1):
            drop = scores[i] - scores[i + 1]
            score_drops.append((i, drop, scores[i]))
        
        max_drop_idx = 0
        max_drop_score = scores[0]
        if score_drops:
            max_drop_idx, _, max_drop_score = max(score_drops, key=lambda x: x[1])
        
        # Define thresholds at different aperture points
        # aperture=0.0: strict (top results only) - mean + 1.5*stdev
        # aperture=0.5: balanced at elbow (biggest score drop)
        # aperture=1.0: permissive (many results) - mean - 1.5*stdev
        strict_threshold = mean_score + (1.5 * stdev)
        elbow_threshold = max_drop_score  # Score AT the elbow
        loose_threshold = max(mean_score - (1.5 * stdev), 0.0)  # Don't go below 0
        
        # Interpolate based on aperture (0.0=strict, 1.0=permissive)
        if aperture <= 0.5:
            # 0.0 -> 0.5: interpolate between strict and elbow
            t = aperture / 0.5  # 0.0-1.0
            threshold = strict_threshold - t * (strict_threshold - elbow_threshold)
        else:
            # 0.5 -> 1.0: interpolate between elbow and loose
            t = (aperture - 0.5) / 0.5  # 0.0-1.0
            threshold = elbow_threshold - t * (elbow_threshold - loose_threshold)
        
        # Filter by threshold
        filtered = [h for h in hits if h["score"] >= threshold]
        
        logger.info(
            f"'{query_text}' - Aperture filter: {len(hits)} results -> {len(filtered)} "
            f"(aperture={aperture}, threshold={threshold:.4f}, elbow_idx={max_drop_idx})"
        )
        
        return filtered
    
    def _to_search_hit(self, hit: Dict[str, Any]) -> SearchHit:
        """Convert raw hit to SearchHit"""
        source = hit["source"]
        
        return SearchHit(
            doc_id=hit["id"],
            score=hit["score"],
            root_id=source.get("root_id", ""),
            version_id=source.get("version_id", ""),
            title=source.get("title", ""),
            description=source.get("description", ""),
            content=source.get("content", ""),
            tags=source.get("tags_canonical", []),
            metadata=source.get("metadata", {}),
            collection_id=source.get("collection_id"),
            owner_id=source.get("owner_id"),
            state=source.get("state"),
            is_head=source.get("is_head"),
            highlights=hit.get("highlight")
        )
