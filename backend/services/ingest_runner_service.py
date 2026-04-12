"""Content extraction utilities for the ingest runner agent.

Downloads S3 content and extracts text for indexing and chunking.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from services.content_service import generate_signed_url
from services.types_service import resolve_capability_target

logger = logging.getLogger(__name__)

# Maximum bytes to download for text extraction
MAX_DOWNLOAD_BYTES = 10_000_000  # 10 MB

# MIME prefixes/types where we can extract raw text
_TEXT_EXTRACTABLE = {
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
    "application/ld+json",
    "application/xhtml+xml",
}


def infer_extraction_handler(content_type: str) -> Optional[str]:
    """Return the handler key required to derive searchable content for *content_type*."""
    if not content_type:
        return None

    # Prefer type-local capability contracts when present.
    declared = resolve_capability_target(content_type, "extract_text")
    if declared:
        return declared

    # Keep a generic fallback when no contract is declared for a MIME.
    return "extract-content"


def describe_content_processing(
    content_type: str,
    *,
    has_inline_content: bool = False,
    upload_complete: bool = True,
) -> dict:
    """Describe whether content can be indexed immediately or needs a handler."""
    deterministic = has_inline_content or is_text_extractable(content_type)
    handler = None if deterministic else infer_extraction_handler(content_type)

    if not upload_complete and not has_inline_content:
        return {
            "strategy": "deterministic" if deterministic else "handler",
            "handler": handler,
            "asset_status": "uploading",
            "content_status": "pending_upload",
            "index_status": "pending_upload",
            "status": "pending_upload",
        }

    if deterministic:
        return {
            "strategy": "deterministic",
            "handler": None,
            "asset_status": "available",
            "content_status": "available",
            "index_status": "ready",
            "status": "ready",
        }

    return {
        "strategy": "handler",
        "handler": handler,
        "asset_status": "available",
        "content_status": "pending_handler",
        "index_status": "pending_handler",
        "status": "pending_handler",
    }


def is_text_extractable(content_type: str) -> bool:
    """Return True if we can extract text directly from this content type."""
    if not content_type:
        return False
    content_type = content_type.lower().split(";")[0].strip()
    if content_type.startswith("text/"):
        return True
    return content_type in _TEXT_EXTRACTABLE


def extract_text_from_s3(
    content_key: str,
    content_type: str,
    filename: Optional[str] = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> Optional[str]:
    """Download an S3 object via signed URL and extract text content.

    Returns the extracted text, or None if extraction isn't possible.
    """
    if not is_text_extractable(content_type):
        logger.info("Content type '%s' not text-extractable, skipping download", content_type)
        return None

    url = generate_signed_url(content_key, filename=filename, content_type=content_type, as_attachment=False)
    if not url:
        logger.warning("Could not generate signed URL for key=%s", content_key)
        return None

    try:
        req = Request(url)
        with urlopen(req, timeout=30) as resp:
            raw = resp.read(max_bytes)
    except (URLError, OSError) as exc:
        logger.warning("Failed to download content for key=%s: %s", content_key, exc)
        return None

    # Detect encoding from Content-Type header or default to utf-8
    encoding = "utf-8"
    content_type_lower = content_type.lower()
    if "charset=" in content_type_lower:
        charset_part = content_type_lower.split("charset=")[-1].split(";")[0].strip()
        encoding = charset_part or "utf-8"

    try:
        text = raw.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        text = raw.decode("utf-8", errors="replace")

    return text if text.strip() else None


def extract_text_from_artifact(artifact) -> Optional[str]:
    """Extract text from an artifact's content or S3 storage.

    Prefers inline content; falls back to S3 download for binary uploads.
    """
    import json

    # Check inline content first
    content = getattr(artifact, "content", None) or ""
    if content.strip():
        return content

    # Parse context for S3 metadata
    raw_ctx = getattr(artifact, "context", None) or ""
    try:
        ctx = json.loads(raw_ctx) if isinstance(raw_ctx, str) else (raw_ctx or {})
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(ctx, dict):
        return None

    content_key = ctx.get("content_key")
    if not content_key:
        return None

    content_type = ctx.get("content_type") or ""
    filename = ctx.get("filename")
    return extract_text_from_s3(content_key, content_type, filename=filename)
