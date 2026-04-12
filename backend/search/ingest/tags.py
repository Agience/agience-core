# search/ingest/tags.py
import logging
import re
from typing import List

logger = logging.getLogger(__name__)


def normalize_tag(tag: str) -> str:
    """
    Normalize a single tag to canonical form.
    
    - Lowercase
    - Strip whitespace
    - Remove special characters (keep alphanumeric, hyphens, underscores)
    """
    if not tag:
        return ""
    
    # Lowercase and strip
    normalized = tag.lower().strip()
    
    # Keep only alphanumeric, hyphens, underscores, spaces
    normalized = re.sub(r"[^a-z0-9\-_\s]", "", normalized)
    
    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized)
    
    return normalized.strip()


def normalize_tags(tags: List[str]) -> List[str]:
    """
    Normalize a list of tags to canonical form.
    
    Returns unique, sorted list of normalized tags.
    """
    if not tags:
        return []
    
    normalized = set()
    for tag in tags:
        if isinstance(tag, str) and tag.strip():
            norm = normalize_tag(tag)
            if norm:
                normalized.add(norm)
    
    return sorted(normalized)


def parse_tags_from_context(context_str: str) -> List[str]:
    """
    Extract tags from artifact context JSON.
    
    Returns list of tag strings.
    """
    import json
    
    if not context_str or not context_str.strip():
        return []
    
    try:
        context = json.loads(context_str) if isinstance(context_str, str) else context_str
        tags = context.get("tags", [])
        
        if isinstance(tags, list):
            return [str(t) for t in tags if t]
        elif isinstance(tags, str):
            # Split comma-separated tags
            return [t.strip() for t in tags.split(",") if t.strip()]
        
        return []
    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        logger.warning(f"Failed to parse tags from context: {e}")
        return []


def extract_metadata_from_context(context_str: str) -> dict:
    """
    Extract searchable metadata from artifact context JSON.
    
    Returns dict with fields like:
    - doc_type
    - content_type
    - filename
    - amount
    - score
    - pii
    """
    import json
    
    metadata = {}
    
    if not context_str or not context_str.strip():
        return metadata
    
    try:
        context = json.loads(context_str) if isinstance(context_str, str) else context_str
        
        # Extract known metadata fields
        if "content_type" in context:
            metadata["content_type"] = context["content_type"]
        
        if "filename" in context:
            metadata["filename"] = context["filename"]
        
        if "doc_type" in context:
            metadata["doc_type"] = context["doc_type"]
        
        # Numeric fields
        if "amount" in context:
            try:
                metadata["amount"] = float(context["amount"])
            except (ValueError, TypeError):
                pass
        
        if "score" in context:
            try:
                metadata["score"] = float(context["score"])
            except (ValueError, TypeError):
                pass
        
        # Boolean fields
        if "pii" in context:
            metadata["pii"] = bool(context["pii"])
        
    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        logger.warning(f"Failed to extract metadata from context: {e}")
    
    return metadata
