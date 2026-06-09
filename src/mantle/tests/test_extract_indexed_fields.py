"""Unit tests for `search.ingest.chunking.extract_indexed_fields` (Step 1.7).

The helper reads a type's `context_schema` index hints (via
`types_service.get_field_index_hints`) and groups context field values by hint
kind. Tests patch the types_service helper so we don't depend on real type
definitions.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from search.ingest.chunking import extract_indexed_fields


def _patch_hints(hints: dict):
    return patch(
        "services.types_service.get_field_index_hints",
        return_value=hints,
    )


def test_no_content_type_returns_empty():
    assert extract_indexed_fields('{"x": "y"}', None) == {}


def test_no_hints_returns_empty():
    with _patch_hints({}):
        assert extract_indexed_fields('{"x": "y"}', "application/vnd.test+json") == {}


def test_invalid_json_returns_empty():
    with _patch_hints({"title": ["lexical"]}):
        assert extract_indexed_fields("not-json", "application/vnd.test+json") == {}


def test_lexical_fields_extracted():
    hints = {"title": ["lexical"], "description": ["lexical"]}
    ctx = json.dumps({"title": "Hello", "description": "World"})
    with _patch_hints(hints):
        result = extract_indexed_fields(ctx, "application/vnd.test+json")
    assert result["lexical"] == ["Hello", "World"]
    assert result["semantic"] == []


def test_field_with_multiple_hints_appears_under_each():
    hints = {"description": ["lexical", "semantic"]}
    ctx = json.dumps({"description": "Both kinds"})
    with _patch_hints(hints):
        result = extract_indexed_fields(ctx, "application/vnd.test+json")
    assert result["lexical"] == ["Both kinds"]
    assert result["semantic"] == ["Both kinds"]


def test_geo_numeric_temporal_fields():
    hints = {
        "location": ["geo"],
        "price": ["numeric"],
        "created_at": ["temporal"],
    }
    ctx = json.dumps({
        "location": "37.77,-122.42",
        "price": 49.99,
        "created_at": "2026-05-07T00:00:00Z",
    })
    with _patch_hints(hints):
        result = extract_indexed_fields(ctx, "application/vnd.test+json")
    assert result["geo"] == ["37.77,-122.42"]
    assert result["numeric"] == ["49.99"]
    assert result["temporal"] == ["2026-05-07T00:00:00Z"]


def test_missing_field_dropped():
    hints = {"title": ["lexical"], "description": ["lexical"]}
    ctx = json.dumps({"title": "Only title"})  # description absent
    with _patch_hints(hints):
        result = extract_indexed_fields(ctx, "application/vnd.test+json")
    assert result["lexical"] == ["Only title"]


def test_empty_string_field_dropped():
    hints = {"title": ["lexical"]}
    ctx = json.dumps({"title": "   "})  # whitespace only
    with _patch_hints(hints):
        result = extract_indexed_fields(ctx, "application/vnd.test+json")
    assert result["lexical"] == []


def test_list_value_serialized_as_json():
    """`sources: [{...}, {...}]` should serialize as JSON so each element's
    text contributes to the BM25 corpus."""
    hints = {"sources": ["lexical"]}
    ctx = json.dumps({"sources": [
        {"artifact_id": "a-1", "excerpt": "key insight", "score": 0.9},
        {"artifact_id": "a-2", "excerpt": "supporting fact", "score": 0.7},
    ]})
    with _patch_hints(hints):
        result = extract_indexed_fields(ctx, "application/vnd.test+json")
    assert len(result["lexical"]) == 1
    serialized = result["lexical"][0]
    assert "key insight" in serialized
    assert "supporting fact" in serialized


def test_dict_value_serialized():
    hints = {"metadata": ["lexical"]}
    ctx = json.dumps({"metadata": {"author": "Alice", "version": 2}})
    with _patch_hints(hints):
        result = extract_indexed_fields(ctx, "application/vnd.test+json")
    assert "Alice" in result["lexical"][0]


def test_context_not_dict_returns_empty():
    """Defensively: if context JSON parses to a non-dict (rare), bail out."""
    hints = {"title": ["lexical"]}
    with _patch_hints(hints):
        result = extract_indexed_fields("[1, 2, 3]", "application/vnd.test+json")
    assert result == {}
