"""S3-backed :class:`PostingStore` + :class:`StatsStore` adapters (Step 2.6.9).

Production wiring of the in-memory stores from :mod:`posting` and
:mod:`stats`. Encrypted blobs persist in S3 (or any S3-compatible store
like MinIO) under::

    {prefix}/{principal_id}/sse/posting/{blind_token}.enc
    {prefix}/{principal_id}/sse/manifests/{artifact_id}.enc
    {prefix}/{principal_id}/sse/stats.enc

The adapters are deliberately independent of :mod:`services.content_service`
so the MANTLE-SSE package can be wired against any boto3-compatible
client. Mirror-images of :class:`S3CellStore` for the same reasons.

Wire format on disk: the raw bytes returned by :func:`pack_posting` /
:func:`pack_manifest` / :func:`pack_stats` (`nonce ‖ ciphertext ‖ tag`).
GCM authentication happens inside the SSE engine on read; these
adapters are thin dictionaries over S3.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _is_not_found(exc: Exception) -> bool:
    """Detect S3 NoSuchKey / 404 across boto3 + minio variants."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = (response.get("Error") or {}).get("Code")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return True
    return type(exc).__name__ in {"NoSuchKey", "404"}


def _join_key(*parts: str) -> str:
    return "/".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# S3PostingStore
# ---------------------------------------------------------------------------


class S3PostingStore:
    """:class:`PostingStore` Protocol implementation backed by an S3 bucket.

    Layout::

        {prefix}/{principal_id}/sse/posting/{blind_token}.enc
        {prefix}/{principal_id}/sse/manifests/{artifact_id}.enc

    Args:
        s3_client: A boto3 S3 client (or compatible). Caller manages
            credentials and endpoint URL.
        bucket: Bucket name. Must already exist; this class does not
            create it.
        prefix: Optional key prefix. Defaults to ``"mantle-sse"``. Empty
            string disables the prefix (blobs live at bucket root).
    """

    def __init__(
        self,
        s3_client: object,
        bucket: str,
        prefix: str = "mantle-sse",
    ) -> None:
        if not bucket:
            raise ValueError("S3PostingStore: bucket name is required")
        self._s3 = s3_client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    def _posting_key(self, principal_id: str, blind_token: str) -> str:
        return _join_key(
            self._prefix, principal_id, "sse", "posting", f"{blind_token}.enc",
        )

    def _manifest_key(self, principal_id: str, artifact_id: str) -> str:
        return _join_key(
            self._prefix, principal_id, "sse", "manifests", f"{artifact_id}.enc",
        )

    def _posting_owner_prefix(self, principal_id: str) -> str:
        return _join_key(self._prefix, principal_id, "sse", "posting") + "/"

    # ------------------------------------------------------------------
    # PostingStore Protocol — postings
    # ------------------------------------------------------------------

    def get_posting(self, principal_id: str, blind_token: str) -> Optional[bytes]:
        return self._get(self._posting_key(principal_id, blind_token))

    def put_posting(self, principal_id: str, blind_token: str, blob: bytes) -> None:
        self._put(self._posting_key(principal_id, blind_token), blob)

    def delete_posting(self, principal_id: str, blind_token: str) -> None:
        self._delete(self._posting_key(principal_id, blind_token))

    def list_tokens_for_owner(self, principal_id: str) -> List[str]:
        prefix = self._posting_owner_prefix(principal_id)
        out: List[str] = []
        for key in self._list_under(prefix):
            if not key.endswith(".enc"):
                continue
            base = key[len(prefix):]
            if base.endswith(".enc"):
                out.append(base[: -len(".enc")])
        return out

    # ------------------------------------------------------------------
    # PostingStore Protocol — manifests
    # ------------------------------------------------------------------

    def get_manifest(self, principal_id: str, artifact_id: str) -> Optional[bytes]:
        return self._get(self._manifest_key(principal_id, artifact_id))

    def put_manifest(self, principal_id: str, artifact_id: str, blob: bytes) -> None:
        self._put(self._manifest_key(principal_id, artifact_id), blob)

    def delete_manifest(self, principal_id: str, artifact_id: str) -> None:
        self._delete(self._manifest_key(principal_id, artifact_id))

    # ------------------------------------------------------------------
    # Shared S3 helpers
    # ------------------------------------------------------------------

    def _get(self, key: str) -> Optional[bytes]:
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            logger.warning("S3PostingStore get failed for %s: %s", key, exc)
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

    def _put(self, key: str, blob: bytes) -> None:
        if not isinstance(blob, (bytes, bytearray)):
            raise TypeError("S3PostingStore.put expects bytes")
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=bytes(blob),
            ContentType="application/octet-stream",
        )

    def _delete(self, key: str) -> None:
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                return
            logger.warning("S3PostingStore delete failed for %s: %s", key, exc)
            raise

    def _list_under(self, prefix: str) -> List[str]:
        keys: List[str] = []
        paginator = getattr(self._s3, "get_paginator", None)
        if paginator is not None:
            pages = list(paginator("list_objects_v2").paginate(
                Bucket=self._bucket, Prefix=prefix,
            ))
        else:
            pages = [self._s3.list_objects_v2(
                Bucket=self._bucket, Prefix=prefix,
            )]
        for page in pages:
            for entry in page.get("Contents", []) or []:
                key = entry.get("Key", "")
                if key:
                    keys.append(key)
        return keys


# ---------------------------------------------------------------------------
# S3StatsStore
# ---------------------------------------------------------------------------


class S3StatsStore:
    """:class:`StatsStore` Protocol implementation backed by an S3 bucket.

    Layout::

        {prefix}/{principal_id}/sse/stats.enc

    One blob per owner. Args mirror :class:`S3PostingStore`.
    """

    def __init__(
        self,
        s3_client: object,
        bucket: str,
        prefix: str = "mantle-sse",
    ) -> None:
        if not bucket:
            raise ValueError("S3StatsStore: bucket name is required")
        self._s3 = s3_client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    def _stats_key(self, principal_id: str) -> str:
        return _join_key(self._prefix, principal_id, "sse", "stats.enc")

    def get(self, principal_id: str) -> Optional[bytes]:
        key = self._stats_key(principal_id)
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            logger.warning("S3StatsStore get failed for %s: %s", key, exc)
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

    def put(self, principal_id: str, blob: bytes) -> None:
        if not isinstance(blob, (bytes, bytearray)):
            raise TypeError("S3StatsStore.put expects bytes")
        self._s3.put_object(
            Bucket=self._bucket,
            Key=self._stats_key(principal_id),
            Body=bytes(blob),
            ContentType="application/octet-stream",
        )

    def delete(self, principal_id: str) -> None:
        try:
            self._s3.delete_object(
                Bucket=self._bucket, Key=self._stats_key(principal_id),
            )
        except Exception as exc:
            if _is_not_found(exc):
                return
            logger.warning("S3StatsStore delete failed for %s: %s", principal_id, exc)
            raise


__all__ = ["S3PostingStore", "S3StatsStore"]
