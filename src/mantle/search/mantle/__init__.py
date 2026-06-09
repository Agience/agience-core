"""MANTLE encrypted search — vector + lexical (Steps 2.0 → 2.6.9).

Public surface:

- :class:`OracleService` — per-owner master keys, HKDF-derived cell + SSE keys
- :class:`MantleIndexer` — FAISS clustering, AES-256-GCM cell encryption, S3 upload
- :class:`MantleQueryEngine` — centroid routing, cell decrypt, ANN over decrypted vectors
- :class:`LightConeResolver` — AQL BFS over origin edges with `propagate` masks
- :mod:`sse` — encrypted lexical (BM25) index per
  ``.dev/features/mantle-sse-lexical-index.md``. Replaces OpenSearch.

The router-shape adapter — :class:`MantleSseSearchAccessor` — and
production wiring builders live under :mod:`sse` and :mod:`wiring`.
The legacy OpenSearch-arm ``MantleSearchAccessor`` was retired with
OpenSearch in Step 2.6.9 part 2.
"""

from __future__ import annotations

from .engine import MantleQueryEngine
from .indexer import MantleIndexer
from .lightcone import LightConeResolver
from .oracle import OracleService

__all__ = [
    "MantleIndexer",
    "MantleQueryEngine",
    "LightConeResolver",
    "OracleService",
]
