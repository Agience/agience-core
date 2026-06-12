"""Unified artifact indexing pipeline (post-OpenSearch retirement).

Every artifact — regardless of content type — goes through the same path:

    artifact (any type, any collection)
      → SSE: tokenize title/description/tags/content → encrypted posting lists
      → MANTLE: chunk content text → embed → encrypted IVF cells

Both arms are unconditional once the wiring prerequisites (Oracle, S3,
Arango) are met. No feature flags. The router converts missing
prerequisites to 503 (no plaintext fallback by design).

OpenSearch was retired in Step 2.6.9 part 2 — the previous BM25 path,
the `bulk_index_documents` calls, and the `_prepare_base_doc` shape
that mirrored the OpenSearch document went away with it.

See `internal design notes` and
`internal design notes`.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from kernel.embeddings import Embeddings, model_id as emb_model_id
from entities.artifact import Artifact

from search.ingest.chunking import (
    chunk_text,
    extract_text_from_context,
    should_chunk_content,
)
from search.ingest.tags import (
    normalize_tags,
    parse_tags_from_context,
)
from services.ingest_runner_service import extract_text_from_artifact

logger = logging.getLogger(__name__)

_embeddings = Embeddings()


# Optional async queue
try:
    from search.ingest import index_queue
except Exception as exc:  # pragma: no cover — queue optional during static analysis
    logger.error("Failed to import index_queue: %s", exc, exc_info=True)
    index_queue = None  # type: ignore[assignment]


# ============================================================
#  Field extraction (shared by SSE + MANTLE)
# ============================================================


def _extract_artifact_fields(artifact: Artifact) -> dict[str, str]:
    """Build the long-form per-field text dict the SSE indexer wants.

    Returns ``{"title": ..., "description": ..., "tags": ..., "content": ...}``,
    omitting empty fields so the indexer skips them. ``content`` here is
    the full analyzable text (artifact.content + extracted text fields)
    — the same corpus the MANTLE chunker walks for embedding.
    """
    text_fields = extract_text_from_context(artifact.context)

    title = (
        text_fields.get("title", "").strip()
        or (getattr(artifact, "name", "") or "").strip()
    )
    description = (
        text_fields.get("description", "").strip()
        or (getattr(artifact, "description", "") or "").strip()
    )

    raw_tags = parse_tags_from_context(artifact.context)
    tags_canonical = normalize_tags(raw_tags)
    tags_text = " ".join(t for t in tags_canonical if t)

    content_text = (extract_text_from_artifact(artifact) or "").strip()
    if not content_text:
        content_text = (artifact.content or "").strip()

    fields: dict[str, str] = {}
    if title:
        fields["title"] = title
    if description:
        fields["description"] = description
    if tags_text:
        fields["tags"] = tags_text
    if content_text:
        fields["content"] = content_text
    return fields


def _build_chunk_id(root_id: str, chunk_id: int) -> str:
    return f"{root_id}:chunk:{chunk_id}"


def _reconcile_native(embeddings: list):
    """Reconcile raw embeddings → native anchor-relative codes against the live
    AnchorSet. Returns ``(codes_or_None, anchorset_model_id_or_None)``, where
    ``codes`` aligns 1:1 with ``embeddings`` (``None`` per item whose dimension
    doesn't match the anchors).

    Geometry layer (canonical plan §1) — no keys/auth. The caller ensures the
    AnchorSet exists first (``require_live_anchorset``); this returns ``None``
    only on an unexpected absence (defensive).
    """
    try:
        from search.anchors.reconciler import Reconciler
        from search.anchors.store import get_crosswalks, get_live_anchorset
    except Exception:
        return None, None
    aset = get_live_anchorset()
    if aset is None or len(aset) == 0:
        return None, None
    try:
        rec = Reconciler(aset, crosswalks=get_crosswalks())
        codes = [
            rec.to_native(emb).to_dict()
            if (emb is not None and len(emb) == aset.dim)
            else None
            for emb in embeddings
        ]
        return codes, aset.model_id
    except Exception:
        logger.debug("MANTLE: native reconcile skipped", exc_info=True)
        return None, aset.model_id


def _density_layers(embeddings: list):
    """Per-chunk density-zoom layer (L0/L1/L2 + density) over the live AnchorSet,
    aligned 1:1 with ``embeddings`` (``None`` per item that can't be placed).
    The caller ensures the AnchorSet exists first; returns ``None`` only on an
    unexpected absence (defensive). Geometry layer (§1)."""
    try:
        from search.anchors.store import get_density_zoom
    except Exception:
        return None
    dz = get_density_zoom()
    if dz is None:
        return None
    dim = dz.anchorset.dim
    out = []
    for emb in embeddings:
        if emb is None or len(emb) != dim:
            out.append(None)
        else:
            layer, dens = dz.layer(emb)
            out.append((layer, round(float(dens), 4)))
    return out


# ============================================================
#  MANTLE vector hook — encrypted IVF, chunks + embeddings
# ============================================================


def _mantle_index_artifact(
    artifact: Artifact,
    collection_id: str,
    fields: dict[str, str],
) -> None:
    """Chunk + embed the artifact's content, write to MANTLE cells."""
    content = fields.get("content", "")
    if not content:
        return

    if not collection_id:
        return

    artifact_root = artifact.root_id or artifact.id

    # Chunk + embed.
    if should_chunk_content(content):
        chunks = list(chunk_text(content))
    else:
        chunks = [{"chunk_id": 0, "text": content}]

    texts = [c["text"] for c in chunks if c.get("text")]
    if not texts:
        return
    try:
        embeddings = _embeddings(texts)
    except Exception:
        logger.warning(
            "MANTLE: embedding failed for artifact %s",
            artifact.id, exc_info=True,
        )
        return
    if not any(embeddings):
        return

    # The AnchorSet is the one coordinate system (canonical plan §3). Ensure it
    # exists — bootstrapping from the seed corpus on first use — so reconcile,
    # density, and routing all see the same anchors. No flat fallback: if it
    # can't be created, skip the vector arm (the commit still succeeds).
    try:
        from search.anchors.store import require_live_anchorset
        require_live_anchorset()
    except Exception:
        logger.warning(
            "MANTLE: AnchorSet unavailable; skipping vector index for %s",
            artifact.id, exc_info=True,
        )
        return

    # Native language: reconcile raw vectors → sparse anchor-relative codes,
    # plus a density-zoom layer. Provenance: model_id per chunk.
    native_codes, anchorset_model_id = _reconcile_native(embeddings)
    density = _density_layers(embeddings)
    chunk_model_id = anchorset_model_id or emb_model_id()

    mantle_chunks = []
    for i, emb in enumerate(embeddings):
        if emb is None:
            continue
        record = {
            "artifact_id": artifact_root,
            "chunk_id": int(chunks[i].get("chunk_id", i)),
            "embedding": emb,
            "text": chunks[i].get("text", ""),
            "model_id": chunk_model_id,
        }
        if native_codes is not None and native_codes[i] is not None:
            record["native"] = native_codes[i]
        if density is not None and density[i] is not None:
            record["density_layer"], record["density"] = density[i]
        mantle_chunks.append(record)
    if not mantle_chunks:
        return

    try:
        from services.dependencies import get_arango_db
        from search.mantle.principal import resolve_cell_principal
        from search.mantle.wiring import build_indexer
    except Exception:
        logger.debug("MANTLE wiring unavailable; skipping vector index", exc_info=True)
        return

    try:
        arango_db = next(get_arango_db())
    except Exception:
        logger.debug("MANTLE: arango handle unavailable; skipping", exc_info=True)
        return

    indexer = build_indexer(arango_db)
    if indexer is None:
        logger.debug("MANTLE indexer prerequisites missing; skipping")
        return

    # The cell-key principal is the collection's immutable origin root (NOT
    # created_by / ownership) — index and query resolve it identically, so the
    # same key is derived at both ends. See search.mantle.principal.
    principal_id = resolve_cell_principal(arango_db, collection_id)
    if not principal_id:
        return

    try:
        touched = indexer.index_artifact(principal_id, collection_id, mantle_chunks)
        logger.info(
            "MANTLE indexed artifact %s (principal=%s collection=%s, %d cells)",
            artifact.id, principal_id, collection_id, touched,
        )
    except Exception:
        logger.warning(
            "MANTLE indexing failed for artifact %s",
            artifact.id, exc_info=True,
        )


def _mantle_remove_artifact(
    principal_id: str, collection_id: str, artifact_id: str,
) -> None:
    """Strip an artifact's chunks from MANTLE cells."""
    try:
        from services.dependencies import get_arango_db
        from search.mantle.wiring import build_indexer
        arango_db = next(get_arango_db())
        indexer = build_indexer(arango_db)
        if indexer is None:
            return
        indexer.remove_artifact(principal_id, collection_id, artifact_id)
    except Exception:
        logger.warning(
            "MANTLE remove failed for artifact %s (owner=%s, collection=%s)",
            artifact_id, principal_id, collection_id, exc_info=True,
        )


# ============================================================
#  MANTLE-SSE hook — encrypted lexical, posting lists
# ============================================================


def _sse_index_artifact(
    artifact: Artifact,
    collection_id: str,
    fields: dict[str, str],
) -> None:
    """Write per-field text into the SSE blind-token posting lists."""
    if not fields:
        return

    if not collection_id:
        return
    artifact_id = artifact.root_id or artifact.id

    try:
        from services.dependencies import get_arango_db
        from search.mantle.principal import resolve_cell_principal
        from search.mantle.wiring import build_sse_indexer
    except Exception:
        logger.debug("SSE wiring unavailable; skipping lexical index", exc_info=True)
        return

    try:
        arango_db = next(get_arango_db())
    except Exception:
        logger.debug("SSE: arango handle unavailable; skipping", exc_info=True)
        return

    indexer = build_sse_indexer(arango_db)
    if indexer is None:
        logger.debug("SSE indexer prerequisites missing; skipping")
        return

    # Same principal as the vector arm: the collection's origin root.
    principal_id = resolve_cell_principal(arango_db, collection_id)
    if not principal_id:
        return

    try:
        n = indexer.index_artifact(principal_id, collection_id, artifact_id, fields)
        logger.info(
            "SSE indexed artifact %s (principal=%s collection=%s, %d tokens)",
            artifact.id, principal_id, collection_id, n,
        )
    except Exception:
        logger.warning(
            "SSE indexing failed for artifact %s",
            artifact.id, exc_info=True,
        )


def _sse_remove_artifact(principal_id: str, artifact_id: str) -> None:
    """Strip an artifact's references from the SSE index."""
    try:
        from services.dependencies import get_arango_db
        from search.mantle.wiring import build_sse_indexer
        arango_db = next(get_arango_db())
        indexer = build_sse_indexer(arango_db)
        if indexer is None:
            return
        indexer.remove_artifact(principal_id, artifact_id)
    except Exception:
        logger.warning(
            "SSE remove failed for artifact %s (owner=%s)",
            artifact_id, principal_id, exc_info=True,
        )


# ============================================================
#  Public API: index / batch / delete
# ============================================================


def index_artifact(
    artifact: Artifact,
    collection_id: str,
    *,
    is_head: bool = True,
) -> bool:
    """Index one artifact into MANTLE vector + MANTLE-SSE lexical.

    Archived artifacts are skipped. ``is_head`` is preserved for caller
    compatibility but no longer drives index branching (there's only one
    physical index per arm now — versioning is artifact-level).
    """
    if artifact.state == Artifact.STATE_ARCHIVED:
        logger.debug("Skipping archived artifact %s", artifact.id)
        return False

    try:
        fields = _extract_artifact_fields(artifact)
        if not fields:
            logger.debug(
                "Artifact %s has no analyzable fields; skipping", artifact.id,
            )
            return False
        _sse_index_artifact(artifact, collection_id, fields)
        _mantle_index_artifact(artifact, collection_id, fields)
        logger.info(
            "Indexed artifact %s in collection %s",
            artifact.id, collection_id,
        )
        return True
    except Exception:
        logger.error(
            "Indexing failed for artifact %s",
            artifact.id, exc_info=True,
        )
        return False


def index_artifacts_batch(
    artifacts: list[Artifact],
    collection_id: str,
    *,
    is_head: bool = True,
) -> bool:
    """Bulk-index a list of artifacts.

    Each artifact runs its own SSE + MANTLE flow. Embedding batching
    happens inside :func:`_mantle_index_artifact` — the MANTLE indexer
    handles per-artifact embedding without cross-artifact batching
    after OpenSearch retirement (the previous bulk path was OpenSearch-
    specific). For very large bulk reindex jobs, the admin command
    runs many of these in parallel via the index queue.
    """
    if not artifacts:
        return True

    start_time = time.time()
    logger.info("Starting bulk index of %d artifacts", len(artifacts))
    indexed = 0
    skipped = 0

    for artifact in artifacts:
        if artifact.state == Artifact.STATE_ARCHIVED:
            skipped += 1
            continue
        if index_artifact(artifact, collection_id, is_head=is_head):
            indexed += 1
        else:
            skipped += 1

    total_time = time.time() - start_time
    logger.info(
        "Bulk indexed %d artifacts (%d skipped) in %.3fs",
        indexed, skipped, total_time,
    )
    return True


def delete_artifact_from_index(
    version_id: str,
    root_id: Optional[str] = None,
    *,
    principal_id: Optional[str] = None,
    collection_id: Optional[str] = None,
) -> bool:
    """Remove an artifact from MANTLE vector + MANTLE-SSE lexical indexes.

    ``principal_id`` is required for both arms. ``collection_id`` is required
    for the MANTLE vector arm (cells are scoped per collection); the SSE
    arm scans the artifact's manifest and removes from every posting
    list it appears in regardless of collection.

    Callers without ``principal_id`` (legacy pre-Step-2.6 paths) get a
    no-op — there's nothing to remove without identity.
    """
    try:
        root = root_id or version_id
        if principal_id and collection_id:
            _mantle_remove_artifact(principal_id, collection_id, root)
        if principal_id:
            _sse_remove_artifact(principal_id, root)
        logger.info("Deleted artifact %s from search", version_id)
        return True
    except Exception:
        logger.error(
            "Failed to delete artifact %s from search",
            version_id, exc_info=True,
        )
        return False


# ============================================================
#  Enqueue helpers
# ============================================================


def enqueue_index_artifact(
    artifact: Artifact,
    collection_id: str,
    *,
    is_head: bool = True,
    tenant_id: Optional[str] = None,
) -> None:
    """Enqueue an artifact for async indexing; falls back to sync."""
    def _act() -> bool:
        return index_artifact(artifact, collection_id, is_head=is_head)

    desc = f"index artifact {artifact.id} -> {collection_id}"
    if index_queue:
        try:
            index_queue.enqueue(_act, description=desc, tenant_id=tenant_id)
            return
        except RuntimeError:
            pass
    logger.debug("Index queue unavailable, indexing synchronously: %s", desc)
    _act()


def enqueue_index_artifacts_batch(
    artifacts: list[Artifact],
    collection_id: str,
    *,
    is_head: bool = True,
    tenant_id: Optional[str] = None,
) -> None:
    """Enqueue a batch for async bulk indexing; falls back to sync."""
    def _act() -> bool:
        return index_artifacts_batch(artifacts, collection_id, is_head=is_head)

    desc = f"batch index {len(artifacts)} artifacts -> {collection_id}"
    if index_queue:
        try:
            index_queue.enqueue(_act, description=desc, tenant_id=tenant_id)
            return
        except RuntimeError:
            pass
    logger.debug("Index queue unavailable, indexing batch synchronously: %s", desc)
    _act()


__all__ = [
    "delete_artifact_from_index",
    "enqueue_index_artifact",
    "enqueue_index_artifacts_batch",
    "index_artifact",
    "index_artifacts_batch",
]
