"""Smoke tests for the MANTLE encrypted-search package skeleton.

Each MANTLE substep has its own dedicated test file. This file only
verifies the package surface imports cleanly. The
``MantleSearchAccessor`` (MANTLE + OpenSearch fusion) was retired in
Step 2.6.9 part 2 alongside OpenSearch.
"""

from __future__ import annotations


def test_public_surface_importable():
    from search.mantle import (
        MantleIndexer,
        MantleQueryEngine,
        LightConeResolver,
        OracleService,
    )
    # Just touching the names is enough — Python resolves them on import.
    assert all(c is not None for c in [
        MantleIndexer, MantleQueryEngine, LightConeResolver, OracleService,
    ])


def test_sse_surface_importable():
    from search.mantle.sse import (
        MantleSseSearchAccessor,
        MantleUnifiedAccessor,
        SseIndexer,
        SseQueryEngine,
    )
    assert all(c is not None for c in [
        MantleSseSearchAccessor, MantleUnifiedAccessor,
        SseIndexer, SseQueryEngine,
    ])
