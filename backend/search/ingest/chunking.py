# search/ingest/chunking.py
import logging
from typing import List, Dict, Any
import tiktoken

from core import config

logger = logging.getLogger(__name__)

# Use cl100k_base encoding (GPT-4, text-embedding-ada-002)
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
