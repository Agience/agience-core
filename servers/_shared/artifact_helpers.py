"""Shared helpers for working with Core artifact responses on MCP servers.

Core uses ``content_type`` in artifact context; MCP convention uses ``mimeType``.
These helpers standardize the translation so every server reads artifact fields
the same way.
"""

from __future__ import annotations

import json
from typing import Any


def parse_artifact_context(artifact: dict) -> dict:
    """Parse artifact context, handling both dict and JSON-string forms."""
    raw = artifact.get("context") or {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw if isinstance(raw, dict) else {}


def get_artifact_content_type(artifact: dict) -> str:
    """Return the lowercased MIME type from a Core artifact response.

    Reads ``context.content_type`` (the Agience canonical field) and strips
    any ``; charset=...`` suffix.  Returns empty string if not set.
    """
    ctx = parse_artifact_context(artifact)
    raw = ctx.get("content_type") or artifact.get("content_type") or ""
    return str(raw).split(";", 1)[0].strip().lower()
