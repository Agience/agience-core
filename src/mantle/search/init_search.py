"""Search initialization (post-OpenSearch retirement).

After Step 2.6.9 part 2 there is no per-startup index creation step —
both MANTLE vector cells and MANTLE-SSE posting lists are S3 objects that
are created lazily on first commit (the indexer auto-bootstraps owner
domains).

What stays here:

- :func:`reindex_all_artifacts` — bulk re-encryption walker. Used as a
  one-shot admin command to populate the encrypted indexes from
  existing artifacts after a key rotation, after a fresh deploy, or as
  the migration command for the OpenSearch → SSE cutover.
- :func:`init_search` — startup hook (no-op shape preserved for
  callers; logs that there's nothing to initialize).
- :func:`shutdown_search` — startup hook (no-op).

The OpenSearch-specific bits (``ensure_search_indices_exist``,
``check_search_health``, ``clear_readonly_blocks``, the ``mappings/``
JSON, the ``opensearch.exceptions`` import) all went with OpenSearch.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

logger = logging.getLogger(__name__)


def init_search() -> None:
    """Startup hook — nothing to initialize after OpenSearch retirement.

    Cells / posting lists / stats blobs are created on first commit by
    the indexer's auto-bootstrap path. This function is kept so the
    main.py lifespan call site stays stable; it just logs.
    """
    logger.info(
        "Search init: MANTLE + MANTLE-SSE use lazy bootstrap (no startup work)."
    )


def shutdown_search() -> None:
    """Shutdown hook — nothing to close. Kept for caller compatibility."""
    pass


def reindex_all_artifacts(*, max_workers: int = 4) -> dict:
    """Bulk-reindex every non-archived artifact into MANTLE + MANTLE-SSE.

    One-shot admin operation. Use cases:

    - Migrating from a previous index (e.g. OpenSearch retirement).
    - Re-encrypting after an owner key rotation.
    - Recovering from a corrupted S3 prefix.

    Queries all artifacts directly from the artifact store and runs the
    standard :func:`pipeline_unified.index_artifact` path on each.
    collection_id is read from the artifact document; root artifacts
    (no parent) self-reference their own id, matching the convention
    used by resolve_authorized_contexts. Idempotent — re-running is safe.

    Returns ``{"indexed": int, "failed": int, "total": int}``.
    """
    from db.arango import COLLECTION_ARTIFACTS, query_documents
    from entities.artifact import Artifact as ArtifactEntity
    from search.ingest.pipeline_unified import index_artifact
    from services.dependencies import get_arango_db

    logger.info("Starting full reindex of all artifacts...")

    db_gen = get_arango_db()
    db = next(db_gen)

    try:
        all_artifacts = list(query_documents(db, ArtifactEntity, COLLECTION_ARTIFACTS, {}))
        logger.info("Found %d artifacts to reindex", len(all_artifacts))

        artifacts_to_index: List[Tuple[str, ArtifactEntity]] = []
        for artifact in all_artifacts:
            if artifact.state == ArtifactEntity.STATE_ARCHIVED:
                continue
            # Root artifacts (no parent collection) self-reference their own id —
            # consistent with resolve_authorized_contexts: doc.get("collection_id") or doc.get("_key").
            collection_id = artifact.collection_id or artifact.id
            artifacts_to_index.append((collection_id, artifact))

        logger.info("Reindexing %d artifacts...", len(artifacts_to_index))

        if not artifacts_to_index:
            return {"indexed": 0, "failed": 0, "total": 0}

        workers = max(1, min(max_workers, len(artifacts_to_index)))
        indexed = 0
        failed = 0

        def index_safe(collection_id: str, artifact: ArtifactEntity) -> bool:
            try:
                return bool(index_artifact(artifact, collection_id, is_head=True))
            except Exception as exc:
                logger.warning(
                    "Reindex failed for %s: %s", artifact.id, exc, exc_info=True,
                )
                return False

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(index_safe, coll_id, artifact)
                for coll_id, artifact in artifacts_to_index
            ]
            for i, future in enumerate(futures, 1):
                try:
                    if future.result():
                        indexed += 1
                    else:
                        failed += 1
                except Exception as exc:
                    failed += 1
                    logger.warning("Unexpected reindex error: %s", exc)
                if i % 50 == 0:
                    logger.info(
                        "  Progress: %d/%d (%d indexed, %d failed)",
                        i, len(futures), indexed, failed,
                    )

        result = {
            "indexed": indexed,
            "failed": failed,
            "total": len(artifacts_to_index),
        }
        logger.info("Reindex complete: %s", result)
        return result

    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


# Backwards-compatible aliases for legacy call sites.
init_search_indices = init_search


def reindex_in_background() -> None:
    """Spawn :func:`reindex_all_artifacts` in a background thread.

    Convenient for admin endpoints that don't want to block on a long
    reindex operation. The thread is daemon-flagged so process shutdown
    doesn't wait on it.
    """
    threading.Thread(target=reindex_all_artifacts, daemon=True).start()


__all__ = [
    "init_search",
    "init_search_indices",
    "reindex_all_artifacts",
    "reindex_in_background",
    "shutdown_search",
]
