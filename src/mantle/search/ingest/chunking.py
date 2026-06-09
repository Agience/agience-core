# search/ingest/chunking.py
import logging
from typing import Any, Dict, List, Optional
import tiktoken

from kernel import config

logger = logging.getLogger(__name__)

# cl100k_base encoding works as a stable token-count proxy across providers.
# Actual embeddings are produced by the configured provider (Agience HTTP).
_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken."""
    return len(_encoder.encode(text))


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> List[Dict[str, Any]]:
    """
    Chunk text into overlapping segments by token count.
    
    Returns list of chunks with:
    - chunk_id: sequential identifier
    - text: chunk content
    - start_token: start position in original text (approx)
    - end_token: end position in original text (approx)
    """
    if chunk_size is None:
        chunk_size = config.SEARCH_CHUNK_SIZE
    if overlap is None:
        overlap = config.SEARCH_CHUNK_OVERLAP

    if not text or not text.strip():
        return []

    # Encode entire text
    tokens = _encoder.encode(text)
    total_tokens = len(tokens)
    
    if total_tokens <= chunk_size:
        # Single chunk
        return [
            {
                "chunk_id": 0,
                "text": text,
                "start_token": 0,
                "end_token": total_tokens,
            }
        ]
    
    chunks = []
    chunk_id = 0
    start = 0
    
    while start < total_tokens:
        # Calculate end position
        end = min(start + chunk_size, total_tokens)
        
        # Extract chunk tokens and decode
        chunk_tokens = tokens[start:end]
        chunk_text = _encoder.decode(chunk_tokens)
        
        chunks.append(
            {
                "chunk_id": chunk_id,
                "text": chunk_text,
                "start_token": start,
                "end_token": end,
            }
        )
        
        chunk_id += 1
        
        # Move start position (with overlap)
        start += chunk_size - overlap
    
    logger.debug(f"Chunked {total_tokens} tokens into {len(chunks)} chunks")
    return chunks


def should_chunk_content(content: str) -> bool:
    """Determine if content should be chunked based on token count."""
    if not content or not content.strip():
        return False
    
    token_count = count_tokens(content)
    return token_count > config.SEARCH_CHUNK_SIZE


def extract_text_from_context(context_str: str) -> Dict[str, str]:
    """
    Extract searchable text fields from artifact context JSON.

    Returns dict with:
    - title: artifact title
    - description: artifact description (PRIMARY search field)
    - tags_raw: comma-separated tags
    """
    import json

    result = {"title": "", "description": "", "tags_raw": ""}

    if not context_str or not context_str.strip():
        return result

    try:
        context = json.loads(context_str) if isinstance(context_str, str) else context_str

        # Extract title
        result["title"] = context.get("title", "")

        # Extract description (PRIMARY search field)
        # Description is human-curated or AI-enhanced for optimal findability
        result["description"] = context.get("description", "")

        # Extract tags
        tags = context.get("tags", [])
        if isinstance(tags, list):
            result["tags_raw"] = ", ".join(str(t) for t in tags if t)
        elif isinstance(tags, str):
            result["tags_raw"] = tags

    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        logger.warning(f"Failed to extract text from context: {e}")

    return result


def extract_indexed_fields(
    context_str: str, content_type: Optional[str]
) -> Dict[str, List[str]]:
    """Extract context fields grouped by their type.json index hints (Step 1.7).

    Reads the type's `context_schema` via :func:`types_service.get_field_index_hints`
    and pulls each declared field's value out of the artifact's context JSON.
    Returns a mapping of hint kind → list of stringified field values, e.g.::

        {"lexical": ["title text", "description text"],
         "semantic": ["offers text", "needs text"],
         "geo": [],
         "numeric": [],
         "temporal": []}

    A field declared with multiple hints (e.g. ``["lexical", "semantic"]``)
    appears under each. Missing or empty values are dropped.

    Returns an empty mapping when the content type has no hints declared OR
    the context isn't valid JSON. Callers should fall back to
    :func:`extract_text_from_context`.

    The OpenSearch ingest pipeline uses the ``lexical`` group today to widen
    the BM25 corpus beyond title/description/tags. ``semantic``/``geo``/
    ``numeric``/``temporal`` are reserved for the MANTLE engine (Step 2.4).
    """
    import json

    if not content_type:
        return {}

    # Lazy import to avoid pulling types_service into search startup.
    from services import types_service

    hints = types_service.get_field_index_hints(content_type)
    if not hints:
        return {}

    if not context_str or not context_str.strip():
        return {}

    try:
        context = (
            json.loads(context_str) if isinstance(context_str, str) else context_str
        )
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "extract_indexed_fields: context isn't valid JSON for %s", content_type
        )
        return {}

    if not isinstance(context, dict):
        return {}

    grouped: Dict[str, List[str]] = {
        "lexical": [], "semantic": [], "geo": [], "numeric": [], "temporal": [],
    }

    for field_name, kinds in hints.items():
        value = context.get(field_name)
        if value is None:
            continue
        # Stringify lists/dicts so the indexer treats them as searchable text.
        if isinstance(value, (dict, list)):
            try:
                stringified = json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                continue
        else:
            stringified = str(value).strip()
        if not stringified:
            continue
        for kind in kinds:
            if kind in grouped:
                grouped[kind].append(stringified)

    return grouped
