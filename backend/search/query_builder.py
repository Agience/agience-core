"""
Query Builder v3.1 - Converts parsed queries to OpenSearch DSL

Bridges query_parser_ output to OpenSearch query format.
"""

from typing import Dict, List, Any, Tuple, Optional
import logging

from core import config
from search.field_weights import load_field_weights
from search.query_parser import (
    ParsedQuery,
    Term,
    FieldFilter,
    TermModifier,
    FieldOperator,
    parse_query
)

logger = logging.getLogger(__name__)


class QueryBuilder:
    """
    Convert ParsedQuery to OpenSearch query DSL.
    """
    
    # Content-type groups for type: filter
    CONTENT_TYPE_GROUPS = {
        "pdf": ["application/pdf"],
        "image": ["image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"],
        "video": ["video/mp4", "video/webm", "video/quicktime", "video/x-msvideo"],
        "audio": ["audio/mpeg", "audio/wav", "audio/ogg", "audio/webm"],
        "text": ["text/plain", "text/markdown", "text/csv"],
        "office": [
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ],
        "docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        "xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
        "pptx": ["application/vnd.openxmlformats-officedocument.presentationml.presentation"],
    }
    
    def __init__(self):
        pass
    
    def build_bm25_query(
        self,
        parsed: ParsedQuery,
        base_filter: Dict[str, Any],
        field_weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Build BM25 bool query from parsed query.
        
        Args:
            parsed: ParsedQuery object
            base_filter: ACL and base filters
            field_weights: Field boost weights (description^10, title^5, etc.)
                          If None, loads from preset specified in config
            
        Returns:
            OpenSearch bool query dict
        """
        if field_weights is None:
            # Load from preset file (configurable, first step to dynamic)
            # Future: could be per-collection or per-user preferences
            try:
                field_weights = load_field_weights(config.SEARCH_FIELD_WEIGHTS_PRESET)
            except Exception as e:
                logger.error(f"Error loading field weights preset, using fallback: {e}")
                # Fallback to description-first defaults
                field_weights = {
                    "description": 10.0,
                    "title": 5.0,
                    "tags_canonical": 3.0,
                    "content": 1.0,
                }
        
        must = []
        should = []
        must_not = []
        
        # Process terms
        for term in parsed.terms:
            query_clause = self._build_term_clause(term, field_weights)
            
            if term.modifier == TermModifier.REQUIRED:
                must.append(query_clause)
            elif term.modifier == TermModifier.EXCLUDED:
                must_not.append(query_clause)
            elif term.modifier == TermModifier.EXACT:
                # Exact match (no stemming)
                exact_clause = self._build_exact_clause(term, field_weights)
                must.append(exact_clause)
            else:
                # Default OR behavior
                should.append(query_clause)
        
        # Process field filters
        filter_clauses = self._build_filter_clauses(parsed.filters)
        must.extend(filter_clauses["must"])
        must_not.extend(filter_clauses["must_not"])
        
        # Add base filter
        if base_filter:
            must.append(base_filter)
        
        # Construct bool query
        bool_query = {}
        if must:
            bool_query["must"] = must
        if should:
            bool_query["should"] = should
            # Always require at least one should clause to match
            # This ensures text terms are required even when filters are present
            bool_query["minimum_should_match"] = 1
        if must_not:
            bool_query["must_not"] = must_not
        
        return {"bool": bool_query}
    
    def _build_term_clause(
        self,
        term: Term,
        field_weights: Dict[str, float]
    ) -> Dict[str, Any]:
        """Build OpenSearch clause for a single term"""
        if term.is_phrase:
            # Phrase match with stemming
            return {
                "multi_match": {
                    "query": term.text,
                    "type": "phrase",
                    "fields": [
                        f"{field}^{weight}"
                        for field, weight in field_weights.items()
                    ]
                }
            }
        else:
            # Single term match with stemming
            # Use best_fields with OR to match "grocery" OR "groceries" after stemming
            return {
                "multi_match": {
                    "query": term.text,
                    "type": "best_fields",
                    "fields": [
                        f"{field}^{weight}"
                        for field, weight in field_weights.items()
                    ],
                    "operator": "or",
                    "fuzziness": "AUTO"
                }
            }
    
    def _build_exact_clause(
        self,
        term: Term,
        field_weights: Dict[str, float]
    ) -> Dict[str, Any]:
        """Build exact match clause (no stemming)"""
        # Use .keyword subfield for exact matching
        if term.is_phrase:
            return {
                "multi_match": {
                    "query": term.text,
                    "type": "phrase",
                    "fields": [
                        "title.keyword",
                        "content",
                        "description"
                    ],
                    "analyzer": "keyword"
                }
            }
        else:
            return {
                "multi_match": {
                    "query": term.text,
                    "fields": ["title.keyword", "content", "description"],
                    "analyzer": "keyword"
                }
            }
    
    def _build_filter_clauses(
        self,
        filters: List[FieldFilter]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build filter clauses from FieldFilter list.
        
        Returns:
            {"must": [...], "must_not": [...]}
        """
        must = []
        must_not = []
        
        for f in filters:
            clause = self._build_field_filter_clause(f)
            if clause:
                if f.negated:
                    must_not.append(clause)
                else:
                    must.append(clause)
        
        return {"must": must, "must_not": must_not}
    
    def _build_field_filter_clause(self, f: FieldFilter) -> Dict[str, Any]:
        """Build OpenSearch clause for a single field filter"""
        # Handle special fields
        if f.field == "tags":
            return self._build_tag_filter(f)
        elif f.field == "type":
            return self._build_type_filter(f)
        elif f.field == "state":
            return self._build_state_filter(f)
        elif f.field in ["size", "created_at", "updated_at"]:
            return self._build_metadata_filter(f)
        elif f.field in ["collection_id", "owner_id"]:
            return self._build_keyword_filter(f)
        else:
            # Custom metadata field
            return self._build_metadata_filter(f)
    
    def _build_tag_filter(self, f: FieldFilter) -> Dict[str, Any]:
        """Build tag filter clause"""
        if f.operator == FieldOperator.SEMANTIC:
            # Semantic tag expansion - placeholder for future
            # For now, just match the tag literally
            logger.warning("Semantic tag expansion not yet implemented")
            return {"term": {"tags_canonical": f.value.lower()}}
        
        # Handle multi-value (comma-separated)
        values = [v.strip().lower() for v in f.value.split(",")]
        
        if len(values) == 1:
            return {"term": {"tags_canonical": values[0]}}
        else:
            return {"terms": {"tags_canonical": values}}
    
    def _build_type_filter(self, f: FieldFilter) -> Dict[str, Any]:
        """Build type filter (maps to MIME types)"""
        # Handle multi-value
        types = [t.strip().lower() for t in f.value.split(",")]
        
        content_types = []
        for t in types:
            if t in self.CONTENT_TYPE_GROUPS:
                content_types.extend(self.CONTENT_TYPE_GROUPS[t])
            else:
                # Assume it's a direct content type
                content_types.append(t)

        if len(content_types) == 1:
            return {"term": {"metadata.content_type": content_types[0]}}
        else:
            return {"terms": {"metadata.content_type": content_types}}
    
    def _build_state_filter(self, f: FieldFilter) -> Dict[str, Any]:
        """Build state filter (workspace only)"""
        # Handle multi-value
        states = [s.strip().lower() for s in f.value.split(",")]
        
        if len(states) == 1:
            return {"term": {"state": states[0]}}
        else:
            return {"terms": {"state": states}}
    
    def _build_metadata_filter(self, f: FieldFilter) -> Dict[str, Any]:
        """Build metadata field filter with range support"""
        field_path = f"metadata.{f.field}" if f.field not in ["size", "created_at", "updated_at"] else f"metadata.{f.field}"
        
        if f.operator == FieldOperator.GT:
            return {"range": {field_path: {"gt": f.value}}}
        elif f.operator == FieldOperator.LT:
            return {"range": {field_path: {"lt": f.value}}}
        elif f.operator == FieldOperator.EXACT:
            return {"term": {f"{field_path}.keyword": f.value}}
        else:
            # Standard equality
            return {"term": {field_path: f.value}}
    
    def _build_keyword_filter(self, f: FieldFilter) -> Dict[str, Any]:
        """Build top-level keyword field filter"""
        if f.operator == FieldOperator.EXACT:
            return {"term": {f.field: f.value}}
        
        # Handle multi-value
        values = [v.strip() for v in f.value.split(",")]
        
        if len(values) == 1:
            return {"term": {f.field: values[0]}}
        else:
            return {"terms": {f.field: values}}


# Convenience functions
def build_query_from_string(
    query_string: str,
    base_filter: Dict[str, Any],
    field_weights: Optional[Dict[str, float]] = None
) -> Tuple[ParsedQuery, Dict[str, Any]]:
    """
    Parse query string and build OpenSearch query.
    
    Returns:
        (ParsedQuery, opensearch_query_dict)
    """
    parsed = parse_query(query_string)
    builder = QueryBuilder()
    opensearch_query = builder.build_bm25_query(parsed, base_filter, field_weights)
    
    return parsed, opensearch_query


if __name__ == "__main__":
    # Test
    builder = QueryBuilder()
    
    test_queries = [
        'machine learning type:pdf',
        '+budget +report tag:finance',
        '="Q1 2025" !draft',
        'innovation type:pdf,docx size:>1000',
    ]
    
    for q in test_queries:
        parsed = parse_query(q)
        query_dsl = builder.build_bm25_query(parsed, {})
        print(f"\nQuery: {q}")
        print(f"Parsed: {parsed}")
        print(f"DSL: {query_dsl}")
