"""Production wiring for MANTLE encrypted search (Step 2.5 + 2.6.9).

Centralizes construction of the MANTLE + SSE pipeline so the router and
the commit-hook indexer share one definition. Each builder pulls the
same Oracle + storage adapters; the choice of accessor vs indexer is
the only fork.

Wiring decisions:

- **Master key store**: :class:`FernetMasterKeyStore` over the platform
  encryption key (:func:`kernel.key_manager.get_encryption_key`). Future
  Shamir-threshold backend swaps in without touching call sites.
- **Cell storage**: :class:`S3CellStore` over Mantle's edge S3 client
  (``services.content_service._s3_edge_internal``) and the configured
  edge bucket. Cells live under
  ``mantle-cells/{owner}/{collection}/{cluster}.cell`` (cluster = routing anchor).
- **SSE posting + stats stores**: S3-backed under ``mantle-sse/`` prefix
  (separate from cell store).

Builders return ``None`` if production stores cannot be constructed
(missing S3 client, missing encryption key). The router treats ``None``
as 503 — no plaintext fallback after OpenSearch retirement.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from .engine import MantleQueryEngine
from .indexer import MantleIndexer
from .lightcone import LightConeResolver
from .oracle import OracleService
from .s3_cell_store import S3CellStore
from .sse import (
    MantleSseSearchAccessor,
    MantleUnifiedAccessor,
    S3PostingStore,
    S3StatsStore,
    SseIndexer,
    SseQueryEngine,
)
from .stores import CellStore

logger = logging.getLogger(__name__)

# Process-level oracle singleton — the FernetMasterKeyStore holds master keys
# in memory. A new instance per call would lose keys between indexing and
# search (different calls share no state), causing every search to generate a
# new key that can't decrypt blobs written by the indexer.
_oracle_singleton: Optional[OracleService] = None
_oracle_lock = threading.Lock()


def _build_oracle() -> Optional[OracleService]:
    """Resolve the platform encryption key and return the process-level Oracle.

    Returns None if the encryption key isn't available — happens during
    setup before key_manager has run.
    """
    global _oracle_singleton
    if _oracle_singleton is not None:
        return _oracle_singleton

    with _oracle_lock:
        if _oracle_singleton is not None:
            return _oracle_singleton

        try:
            from .key_provider import build_key_provider
            from .oracle import ArangoMasterKeyStore
        except Exception as exc:
            logger.warning("MANTLE oracle imports failed: %s", exc)
            return None

        try:
            # KEK custody is pluggable (local file | KMS | Vault) via
            # MANTLE_KEK_PROVIDER — default 'local' = the platform encryption.key.
            kek = build_key_provider()
        except Exception as exc:
            logger.warning("MANTLE oracle: KEK provider unavailable: %s", exc)
            return None

        # Durable, Arango-backed master key store: per-principal DEKs are
        # Fernet-wrapped by the platform KEK and persisted in `mantle_master_keys`,
        # so they survive a mantle restart. The in-process FernetMasterKeyStore
        # lost them on every restart, orphaning all encrypted cells (search → empty).
        from kernel import config as _config
        from schemas.arango.initialize import get_arangodb_connection

        _db_cache: dict = {}

        def _master_key_db():
            db = _db_cache.get("db")
            if db is None:
                db = get_arangodb_connection(
                    _config.ARANGO_HOST,
                    _config.ARANGO_PORT,
                    _config.ARANGO_USERNAME,
                    _config.ARANGO_PASSWORD,
                    _config.ARANGO_DATABASE,
                )
                _db_cache["db"] = db
            return db

        _oracle_singleton = OracleService(ArangoMasterKeyStore(kek, _master_key_db))
        return _oracle_singleton


def _build_cell_store() -> Optional[CellStore]:
    """Construct the S3-backed cell store.

    Reuses Mantle's existing edge S3 client + bucket so MANTLE cells share
    the same MinIO/S3 endpoint as content blobs. They live under a
    distinct prefix so listing the content bucket doesn't tangle with
    artifact uploads.
    """
    try:
        from services import content_service
    except Exception as exc:
        logger.warning("MANTLE cell store: content_service import failed: %s", exc)
        return None

    s3_client = getattr(content_service, "_s3_edge_internal", None)
    bucket = getattr(content_service, "_EDGE_BUCKET", None)
    if s3_client is None or not bucket:
        logger.warning(
            "MANTLE cell store: edge S3 client or bucket not initialized"
        )
        return None

    return S3CellStore(s3_client, bucket=bucket, prefix="mantle-cells")


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_indexer(arango_db: object) -> Optional[MantleIndexer]:
    """Construct a production-wired :class:`MantleIndexer` for commit-time use."""
    oracle = _build_oracle()
    cells = _build_cell_store()
    if oracle is None or cells is None:
        return None
    return MantleIndexer(oracle, cells)


# ---------------------------------------------------------------------------
# MANTLE-SSE wiring (Step 2.6.9)
# ---------------------------------------------------------------------------


def _build_sse_stores() -> Optional[tuple[S3PostingStore, S3StatsStore]]:
    """Construct S3-backed posting + stats stores.

    Reuses Mantle's existing edge S3 client + bucket. SSE blobs live under
    the ``mantle-sse`` prefix, distinct from MANTLE cells (``mantle-cells``)
    and content artifacts. Returns ``None`` if the S3 client / bucket
    aren't initialized — same fallback policy as :func:`_build_cell_store`.
    """
    try:
        from services import content_service
    except Exception as exc:
        logger.warning("MANTLE-SSE stores: content_service import failed: %s", exc)
        return None

    s3_client = getattr(content_service, "_s3_edge_internal", None)
    bucket = getattr(content_service, "_EDGE_BUCKET", None)
    if s3_client is None or not bucket:
        logger.warning(
            "MANTLE-SSE stores: edge S3 client or bucket not initialized"
        )
        return None

    return (
        S3PostingStore(s3_client, bucket=bucket, prefix="mantle-sse"),
        S3StatsStore(s3_client, bucket=bucket, prefix="mantle-sse"),
    )


def build_sse_indexer(arango_db: object) -> Optional[SseIndexer]:
    """Construct a production-wired :class:`SseIndexer` for commit-time use.

    Returns ``None`` if any prerequisite is missing — Oracle, S3, or
    bucket. The caller (commit-path hook) skips SSE indexing on ``None``
    rather than silently using in-memory stores.
    """
    oracle = _build_oracle()
    stores = _build_sse_stores()
    if oracle is None or stores is None:
        return None
    posting_store, stats_store = stores
    return SseIndexer(oracle, posting_store, stats_store)


def build_unified_accessor(
    arango_db: object,
    *,
    field_boosts: Optional[dict] = None,
    rrf_k: int = 60,
) -> Optional[MantleUnifiedAccessor]:
    """Construct a production-wired :class:`MantleUnifiedAccessor`.

    Composes the SSE query engine + the MANTLE vector engine via RRF.
    The vector arm is optional — if the MANTLE cell store
    aren't available, the unified accessor runs SSE-only. The SSE arm
    is required.

    Returns ``None`` if SSE prerequisites are missing — without SSE
    there's nothing to fuse. ``field_boosts`` is forwarded to the SSE
    query engine.
    """
    oracle = _build_oracle()
    sse_stores = _build_sse_stores()
    if oracle is None or sse_stores is None:
        return None
    posting_store, stats_store = sse_stores
    sse_engine = SseQueryEngine(
        oracle, posting_store, stats_store,
        field_boosts=field_boosts,
    )

    # Vector arm — best-effort. Missing MANTLE cell store → SSE-only fusion.
    mantle_engine: Optional[MantleQueryEngine] = None
    mantle_cells = _build_cell_store()
    if mantle_cells is not None:
        mantle_engine = MantleQueryEngine(oracle, mantle_cells)

    return MantleUnifiedAccessor(
        sse_engine, mantle_engine=mantle_engine, rrf_k=rrf_k,
    )


def build_sse_search_accessor(
    arango_db: object,
    *,
    field_boosts: Optional[dict] = None,
    rrf_k: int = 60,
) -> Optional[MantleSseSearchAccessor]:
    """Construct a router-shape (``SearchQuery → SearchResult``) SSE accessor.

    Composes :func:`build_unified_accessor` with the light-cone resolver
    and a ``SearchHit`` hydrator over Arango. This is the canonical
    search backend the artifacts router uses after OpenSearch retirement.

    Returns ``None`` if SSE prerequisites are missing — the router
    converts that to 503 (no plaintext fallback by design).
    """
    unified = build_unified_accessor(
        arango_db, field_boosts=field_boosts, rrf_k=rrf_k,
    )
    if unified is None:
        return None
    resolver = LightConeResolver(arango_db)
    return MantleSseSearchAccessor(unified, resolver, arango_db=arango_db)


__all__ = [
    "build_indexer",
    "build_sse_indexer",
    "build_sse_search_accessor",
    "build_unified_accessor",
]
