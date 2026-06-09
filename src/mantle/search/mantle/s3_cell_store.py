"""S3-backed :class:`CellStore` adapter (MANTLE Step 2.5).

Production wiring of the in-memory :class:`InMemoryCellStore` from
``mantle/search/mantle/stores.py``. Encrypted cell blobs persist in S3 (or
any S3-compatible store such as MinIO) under::

    {prefix}/{principal_id}/{collection_id}/{cluster_id}.cell

One cell per ``(principal_id, collection_id, cluster_id)`` where the cluster is the
routing anchor (canonical plan §5.1) — one path, no flat cell.
The adapter is deliberately independent of :mod:`services.content_service`
so the MANTLE package can be wired against any boto3-compatible client. The
caller (router / app startup) supplies the client + bucket + prefix; this
module knows nothing about the platform's other S3 layouts.

Wire format on disk: the raw bytes returned by :func:`cell.pack_cell`
(`nonce ‖ ciphertext ‖ tag`). MANTLE's crypto module does the integrity
check on read; this adapter is a thin dictionary over S3.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class S3CellStore:
    """:class:`CellStore` Protocol implementation backed by an S3 bucket.

    Args:
        s3_client: A boto3 S3 client (or compatible). Caller manages
            credentials and endpoint URL.
        bucket: Bucket name. The bucket must already exist; this class
            does not create it.
        prefix: Optional key prefix, applied as ``{prefix}/{principal_id}/...``.
            Defaults to ``"mantle-cells"``. Empty string disables the
            prefix (cells live at bucket root).

    The adapter is thread-safe to the same extent boto3 clients are
    (boto3 docs: clients are thread-safe).
    """

    def __init__(self, s3_client: object, bucket: str, prefix: str = "mantle-cells") -> None:
        if not bucket:
            raise ValueError("S3CellStore: bucket name is required")
        self._s3 = s3_client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    def _cell_key(self, principal_id: str, collection_id: str, cluster_id: str = "") -> str:
        # One layout — every cell is anchor-routed:
        #   {prefix}/{owner}/{collection}/{cluster}.cell
        parts = [self._prefix] if self._prefix else []
        parts.extend([principal_id, collection_id, f"{cluster_id}.cell"])
        return "/".join(parts)

    def _owner_prefix(self, principal_id: str) -> str:
        parts = [self._prefix] if self._prefix else []
        parts.append(principal_id)
        return "/".join(parts) + "/"

    def _collection_prefix(self, principal_id: str, collection_id: str) -> str:
        parts = [self._prefix] if self._prefix else []
        parts.extend([principal_id, collection_id])
        return "/".join(parts) + "/"

    # ------------------------------------------------------------------
    # CellStore Protocol
    # ------------------------------------------------------------------

    def get(self, principal_id: str, collection_id: str, cluster_id: str = "") -> Optional[bytes]:
        key = self._cell_key(principal_id, collection_id, cluster_id)
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            # boto3 raises ClientError for 404; we treat any read miss as
            # "no cell" since the indexer always knows whether a cell
            # should exist via the centroid index.
            if _is_not_found(exc):
                return None
            logger.warning("S3CellStore get failed for %s: %s", key, exc)
            raise
        body = resp.get("Body")
        if body is None:
            return None
        try:
            return body.read()
        finally:
            try:
                body.close()
            except Exception:
                pass

    def put(self, principal_id: str, collection_id: str, blob: bytes, cluster_id: str = "") -> None:
        if not isinstance(blob, (bytes, bytearray)):
            raise TypeError("S3CellStore.put expects bytes")
        key = self._cell_key(principal_id, collection_id, cluster_id)
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=bytes(blob),
            ContentType="application/octet-stream",
        )

    def delete(self, principal_id: str, collection_id: str, cluster_id: str = "") -> None:
        key = self._cell_key(principal_id, collection_id, cluster_id)
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                return
            logger.warning("S3CellStore delete failed for %s: %s", key, exc)
            raise

    def _pages(self, prefix: str) -> list:
        paginator = getattr(self._s3, "get_paginator", None)
        if paginator is not None:
            return list(paginator("list_objects_v2").paginate(Bucket=self._bucket, Prefix=prefix))
        return [self._s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix)]

    def list_cells(self, principal_id: str) -> List[str]:
        prefix = self._owner_prefix(principal_id)
        results: set[str] = set()
        for page in self._pages(prefix):
            for entry in page.get("Contents", []) or []:
                cid = _parse_cell_key(entry.get("Key", ""), prefix)
                if cid is not None:
                    results.add(cid)
        return list(results)

    def list_clusters(self, principal_id: str, collection_id: str) -> List[str]:
        """Cluster ids (routing anchors) stored for one context, so removal /
        admin paths can scan every cell of a collection."""
        results: List[str] = []
        prefix = self._collection_prefix(principal_id, collection_id)
        for page in self._pages(prefix):
            for entry in page.get("Contents", []) or []:
                key = entry.get("Key", "")
                if not key.startswith(prefix):
                    continue
                suffix = key[len(prefix):]
                if suffix.endswith(".cell") and "/" not in suffix:
                    results.append(suffix[: -len(".cell")])
        return results


def _parse_cell_key(key: str, owner_prefix: str) -> Optional[str]:
    """Extract ``collection_id`` from an S3 cell key.

    ``{owner}/{collection}/{cluster}.cell`` → ``collection`` (first segment).

    Returns None for keys that don't look like a MANTLE cell key under
    ``owner_prefix`` (defensive; skip stray objects rather than crash).
    """
    if not key.startswith(owner_prefix):
        return None
    suffix = key[len(owner_prefix):]
    if not suffix.endswith(".cell"):
        return None
    inner = suffix[: -len(".cell")]
    if not inner:
        return None
    return inner.split("/", 1)[0]


def _is_not_found(exc: Exception) -> bool:
    """Detect S3 NoSuchKey / 404 across boto3 + minio variants."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = (response.get("Error") or {}).get("Code")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return True
    return type(exc).__name__ in {"NoSuchKey", "404"}


__all__ = ["S3CellStore"]
