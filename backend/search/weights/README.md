# Search Field Weight Presets

Status: **Reference**
Date: 2026-03-31

This directory contains configurable field boost presets for BM25 lexical search.

## Available Presets

### `description-first.json` (DEFAULT)
**Philosophy**: Human curation over raw content

Strongly prioritizes human-curated descriptions. Best for Agience's core use case where artifacts have thoughtful, hand-written descriptions.

- **description**: 10× - Highest quality, human-curated
- **title**: 5× - Concise, intentional
- **tags**: 3× - Curated metadata
- **content**: 1× - Extracted text baseline

**Use when**: Collections are well-curated with quality descriptions

---

### `balanced.json`
**Philosophy**: Moderate emphasis on all fields

Good starting point for diverse content types or when description quality varies.

- **description**: 5× - Still preferred but not dominant
- **title**: 3× - Good signal
- **tags**: 2× - Useful metadata
- **content**: 1× - Baseline

**Use when**: Mixed content quality, general-purpose collections

---

### `content-heavy.json`
**Philosophy**: Full-text search over metadata

Lower boost differential — content has more influence. Good for document archives where descriptions may be sparse or auto-generated.

- **description**: 3× - Light preference
- **title**: 2× - Modest boost
- **tags**: 1.5× - Slight preference
- **content**: 1× - More influential

**Use when**: Large document collections, sparse metadata, full-text search focus

---

## Configuration

Set the active preset via environment variable:

```bash
# .env or .env.local
SEARCH_FIELD_WEIGHTS_PRESET=description-first  # default
# SEARCH_FIELD_WEIGHTS_PRESET=balanced
# SEARCH_FIELD_WEIGHTS_PRESET=content-heavy
```

Weights are loaded at startup from `backend/search/weights/{preset}.json`.

---

## Creating Custom Presets

Add a new JSON file with this structure:

```json
{
  "name": "custom-preset",
  "description": "Brief description of use case",
  "field_boosts": {
    "description": 8.0,
    "title": 4.0,
    "tags_canonical": 2.5,
    "content": 1.0
  },
  "notes": [
    "When to use this preset",
    "Key characteristics",
    "Expected behavior"
  ]
}
```

Then set `SEARCH_FIELD_WEIGHTS_PRESET=custom-preset` in your environment.

---

## Technical Notes

- Boosts are applied in OpenSearch `multi_match` queries as field weights: `"description^10.0"`
- Content field always has boost of 1.0 (baseline) — other fields are relative to this
- Weights multiply the BM25 score for matches in that field
- Higher weights → stronger influence on final ranking
- See `backend/search/query_builder.py` for implementation
