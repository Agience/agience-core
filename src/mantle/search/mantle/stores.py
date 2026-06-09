"""Storage protocols for MANTLE encrypted search (Step 2.2b.iii).

One abstract store that the indexer + query engine talk to:

- :class:`CellStore` — encrypted cell blobs, one per
  ``(principal_id, collection_id, cluster_id)`` where ``cluster_id`` is the routing
  anchor (canonical plan §5.1: the AnchorSet IS the partition). Production backs
  this with S3 (``mantle-cells/{principal_id}/{collection_id}/{cluster_id}.cell``).
  Tests use the in-memory implementation here.

There is ONE path — every cell is anchor-routed; there is no flat / unpartitioned
cell. The set of clusters grows with the manifold (``anchors.grow``).
"""

from __future__ import annotations

import logging
import threading
from typing import List, Optional, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CellStore
# ---------------------------------------------------------------------------

class CellStore(Protocol):
    """Encrypted cell blob storage.

    Cells are addressed by ``(principal_id, collection_id, cluster_id)`` where the
    cluster is the routing anchor (canonical plan §5.1).
    :meth:`OracleService.derive_cell_key` derives a distinct AES-256-GCM key per
    tuple. The product always supplies a real anchor id — there is no flat cell.

    Production S3 layout:
      ``mantle-cells/{principal_id}/{collection_id}/{cluster_id}.cell``
    """

    def get(self, principal_id: str, collection_id: str, cluster_id: str = "") -> Optional[bytes]:
        """Return the cell blob for the tuple, or None."""

    def put(self, principal_id: str, collection_id: str, blob: bytes, cluster_id: str = "") -> None:
        """Persist (or overwrite) the cell blob."""

    def delete(self, principal_id: str, collection_id: str, cluster_id: str = "") -> None:
        """Remove the cell. No-op if absent."""

    def list_cells(self, principal_id: str) -> List[str]:
        """Return distinct ``collection_id`` strings under ``principal_id``."""

    def list_clusters(self, principal_id: str, collection_id: str) -> List[str]:
        """Return the ``cluster_id`` strings stored for one context."""


class InMemoryCellStore:
    """Thread-safe dict-backed CellStore. Test default; not durable."""

    def __init__(self) -> None:
        self._cells: dict[tuple[str, str, str], bytes] = {}
        self._lock = threading.RLock()

    def get(self, principal_id: str, collection_id: str, cluster_id: str = "") -> Optional[bytes]:
        with self._lock:
            return self._cells.get((principal_id, collection_id, cluster_id))

    def put(self, principal_id: str, collection_id: str, blob: bytes, cluster_id: str = "") -> None:
        with self._lock:
            self._cells[(principal_id, collection_id, cluster_id)] = blob

    def delete(self, principal_id: str, collection_id: str, cluster_id: str = "") -> None:
        with self._lock:
            self._cells.pop((principal_id, collection_id, cluster_id), None)

    def list_cells(self, principal_id: str) -> List[str]:
        with self._lock:
            return list({cid for (oid, cid, _clu) in self._cells if oid == principal_id})

    def list_clusters(self, principal_id: str, collection_id: str) -> List[str]:
        with self._lock:
            return [
                clu for (oid, cid, clu) in self._cells
                if oid == principal_id and cid == collection_id
            ]


__all__ = [
    "CellStore",
    "InMemoryCellStore",
]
