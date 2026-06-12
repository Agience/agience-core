"""MantleIndexer — commit-path AES-256-GCM cell encryption + S3 upload.

Step 2.2b.iii implementation. Combines:

- :class:`OracleService` (Step 2.2a) — derives per-cell AES-256-GCM keys
- :func:`cell.pack_cell` / :func:`cell.unpack_cell` (Step 2.2b.i) — round-trip crypto
- :class:`CellStore` (this step) — abstract storage

One cell per ``(principal_id, collection_id, cluster_id)`` where the cluster is the
routing anchor (canonical plan §5.1: the AnchorSet IS the partition). Every
chunk is routed to its nearest anchor — one path, no flat cell.

API:

- :meth:`index_artifact` — upsert chunks into the collection cell and write
- :meth:`remove_artifact` — strip an artifact's chunks from the cell

See `internal design notes` § Layer 2b.
"""

from __future__ import annotations

import logging
from typing import Iterable, List

from . import cell as cell_mod
from .oracle import OracleService
from .stores import CellStore

logger = logging.getLogger(__name__)


class MantleIndexer:
    """Commit-path indexer for MANTLE encrypted search."""

    def __init__(
        self,
        oracle: OracleService,
        cell_store: CellStore,
    ) -> None:
        self._oracle = oracle
        self._cells = cell_store

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def index_artifact(
        self,
        principal_id: str,
        collection_id: str,
        artifact_chunks: Iterable[dict],
    ) -> int:
        """Upsert every chunk into the collection's cell and write.

        Each chunk dict must carry ``artifact_id``, ``chunk_id``, and an
        ``embedding`` (sequence of floats). Additional fields are preserved
        verbatim in the cell.

        Each chunk is routed to the cell of its nearest anchor, so an artifact's
        chunks may span several cells of the collection.

        Returns the number of cells touched, 0 if there were no chunks.
        """
        if not principal_id:
            raise ValueError("principal_id is required")
        if not collection_id:
            raise ValueError("collection_id is required")

        chunks = list(artifact_chunks)
        if not chunks:
            return 0

        # Validate every chunk before mutating the cell (fail-fast).
        for chunk in chunks:
            if not isinstance(chunk, dict):
                raise ValueError("each chunk must be a dict")
            if "artifact_id" not in chunk or "chunk_id" not in chunk:
                raise ValueError("each chunk must carry artifact_id and chunk_id")
            if "embedding" not in chunk:
                raise ValueError("each chunk must carry embedding")

        # Route each chunk to its nearest-anchor cell (canonical plan §5.1).
        # The AnchorSet is mandatory (bootstrapped from the seed corpus on first
        # use); routing has no flat fallback. Re-routing after an AnchorSet
        # change is handled by a full reindex, not here.
        from search.anchors.routing import route_vector
        from search.anchors.store import require_live_anchorset

        anchorset = require_live_anchorset()
        groups: dict[str, List[dict]] = {}
        for chunk in chunks:
            cluster = route_vector(anchorset, chunk.get("embedding"))
            groups.setdefault(cluster, []).append(chunk)

        for cluster_id, records in groups.items():
            self._upsert_into_cell(principal_id, collection_id, records, cluster_id)
        return len(groups)

    def _upsert_into_cell(
        self,
        principal_id: str,
        collection_id: str,
        records: List[dict],
        cluster_id: str = "",
    ) -> None:
        """Read-modify-write one (owner, collection, cluster) cell."""
        key = self._oracle.derive_cell_key(principal_id, collection_id, cluster_id)
        aad = cell_mod.cell_aad(collection_id, cluster_id)
        existing_blob = self._cells.get(principal_id, collection_id, cluster_id)
        existing_chunks = (
            cell_mod.unpack_cell(existing_blob, key, collection_id=aad) if existing_blob else []
        )
        for record in records:
            cell_mod.upsert_chunk(existing_chunks, record)
        new_blob = cell_mod.pack_cell(existing_chunks, key, collection_id=aad)
        self._cells.put(principal_id, collection_id, new_blob, cluster_id)

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    def remove_artifact(
        self, principal_id: str, collection_id: str, artifact_id: str
    ) -> int:
        """Strip every chunk record for ``artifact_id`` from the collection cell.

        Returns 1 if the cell was touched, 0 if the artifact had no chunks.
        """
        if not principal_id or not collection_id or not artifact_id:
            raise ValueError("principal_id, collection_id, artifact_id all required")

        # An artifact's chunks may span several anchor clusters — strip it from
        # every cell of the collection.
        touched = 0
        for cluster_id in self._cells.list_clusters(principal_id, collection_id):
            blob = self._cells.get(principal_id, collection_id, cluster_id)
            if not blob:
                continue
            key = self._oracle.derive_cell_key(principal_id, collection_id, cluster_id)
            aad = cell_mod.cell_aad(collection_id, cluster_id)
            chunks = cell_mod.unpack_cell(blob, key, collection_id=aad)
            before = len(chunks)
            chunks = cell_mod.remove_artifact_chunks(chunks, artifact_id)
            if len(chunks) == before:
                continue
            if not chunks:
                self._cells.delete(principal_id, collection_id, cluster_id)
            else:
                self._cells.put(
                    principal_id, collection_id,
                    cell_mod.pack_cell(chunks, key, collection_id=aad),
                    cluster_id,
                )
            touched += 1
        return touched

    # ------------------------------------------------------------------
    # Inspection helpers (mainly for tests / admin)
    # ------------------------------------------------------------------

    def cells_for(self, principal_id: str) -> List[str]:
        """Return ``collection_id`` strings for each cell stored under
        ``principal_id``. Useful for tests + admin reports."""
        return self._cells.list_cells(principal_id)

    def chunks_in_cell(
        self, principal_id: str, collection_id: str, cluster_id: str = ""
    ) -> List[dict]:
        """Decrypt a single (owner, collection, cluster) cell and return its
        chunk records. Convenience for tests + admin tooling; production callers
        go through :class:`MantleQueryEngine` (Step 2.3).
        """
        blob = self._cells.get(principal_id, collection_id, cluster_id)
        if blob is None:
            return []
        key = self._oracle.derive_cell_key(principal_id, collection_id, cluster_id)
        aad = cell_mod.cell_aad(collection_id, cluster_id)
        return cell_mod.unpack_cell(blob, key, collection_id=aad)

    def collection_chunks(
        self, principal_id: str, collection_id: str
    ) -> List[dict]:
        """Decrypt every cell of a collection (all routing anchors) and return
        the union of chunk records. An artifact's chunks may span several anchor
        cells, so this is the way to read a whole collection. Admin / test
        convenience; production reads go through :class:`MantleQueryEngine`.
        """
        out: List[dict] = []
        for cluster_id in self._cells.list_clusters(principal_id, collection_id):
            out.extend(self.chunks_in_cell(principal_id, collection_id, cluster_id))
        return out
