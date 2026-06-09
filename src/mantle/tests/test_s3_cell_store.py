"""Tests for the S3-backed CellStore adapter (MANTLE Step 2.5).

Covers key construction, get/put/delete/list semantics, paginated listing,
and graceful handling of S3 ``NoSuchKey`` on read/delete.

Uses a hand-rolled fake S3 client rather than moto so the test suite stays
dependency-free. The fake mirrors only the surface the adapter actually
calls (``get_object``, ``put_object``, ``delete_object``,
``list_objects_v2``, ``get_paginator``) and raises a
ClientError-shaped exception for missing keys.
"""

from __future__ import annotations

from typing import Optional

import pytest

from search.mantle.s3_cell_store import S3CellStore


# ---------------------------------------------------------------------------
# Fake S3 client
# ---------------------------------------------------------------------------

class _NoSuchKey(Exception):
    """Raise this from the fake to mimic boto3 ``ClientError(NoSuchKey)``."""

    def __init__(self) -> None:
        super().__init__("NoSuchKey")
        self.response = {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}


class _FakePaginator:
    def __init__(self, client: "_FakeS3Client", method: str) -> None:
        self._client = client
        self._method = method

    def paginate(self, **kwargs):
        # Simple single-page paginator backed by the underlying list call.
        yield self._client.list_objects_v2(**kwargs)


class _FakeS3Client:
    """Just enough boto3 surface for S3CellStore tests."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    # ---- read/write -----------------------------------------------------

    def put_object(self, *, Bucket: str, Key: str, Body: bytes,
                   ContentType: Optional[str] = None) -> dict:
        self.objects[(Bucket, Key)] = bytes(Body)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        try:
            data = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise _NoSuchKey() from exc

        class _Body:
            def __init__(self, b: bytes) -> None:
                self._b = b
                self._read = False

            def read(self) -> bytes:
                self._read = True
                return self._b

            def close(self) -> None:
                pass

        return {"Body": _Body(data), "ContentType": "application/octet-stream"}

    def delete_object(self, *, Bucket: str, Key: str) -> dict:
        self.objects.pop((Bucket, Key), None)
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

    # ---- listing --------------------------------------------------------

    def list_objects_v2(self, *, Bucket: str, Prefix: str = "") -> dict:
        contents = [
            {"Key": k, "Size": len(v)}
            for (b, k), v in self.objects.items()
            if b == Bucket and k.startswith(Prefix)
        ]
        return {"Contents": contents}

    def get_paginator(self, name: str) -> _FakePaginator:
        return _FakePaginator(self, name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestKeyConstruction:
    def test_default_prefix(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        # Internal helper exercised via put + list round-trip below; here
        # we just assert the prefix sticks.
        assert store._prefix == "mantle-cells"

    def test_custom_prefix(self):
        store = S3CellStore(_FakeS3Client(), bucket="b", prefix="custom/path")
        assert store._prefix == "custom/path"

    def test_bucket_required(self):
        with pytest.raises(ValueError):
            S3CellStore(_FakeS3Client(), bucket="")

    def test_empty_prefix_allowed(self):
        store = S3CellStore(_FakeS3Client(), bucket="b", prefix="")
        store.put("o-1", "col-A", b"blob", "anchorX")
        # With empty prefix: {owner}/{collection}/{cluster}.cell
        assert ("b", "o-1/col-A/anchorX.cell") in store._s3.objects
        assert store.get("o-1", "col-A", "anchorX") == b"blob"


class TestPutGetRoundTrip:
    def test_round_trip(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        store.put("o-1", "col-A", b"hello")
        assert store.get("o-1", "col-A") == b"hello"

    def test_overwrite(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        store.put("o-1", "col-A", b"v1")
        store.put("o-1", "col-A", b"v2")
        assert store.get("o-1", "col-A") == b"v2"

    def test_get_missing_returns_none(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        assert store.get("o-1", "col-A") is None

    def test_put_rejects_non_bytes(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        with pytest.raises(TypeError):
            store.put("o-1", "col-A", "not bytes")  # type: ignore[arg-type]

    def test_put_accepts_bytearray(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        store.put("o-1", "col-A", bytearray(b"buf"))
        assert store.get("o-1", "col-A") == b"buf"


class TestDelete:
    def test_delete_existing(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        store.put("o-1", "col-A", b"x")
        store.delete("o-1", "col-A")
        assert store.get("o-1", "col-A") is None

    def test_delete_missing_is_no_op(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        store.delete("o-1", "col-A")  # should not raise

    def test_delete_propagates_other_errors(self):
        class _BadClient(_FakeS3Client):
            def delete_object(self, *, Bucket, Key):
                raise RuntimeError("S3 down")

        store = S3CellStore(_BadClient(), bucket="b")
        store.put("o-1", "col-A", b"x")
        with pytest.raises(RuntimeError):
            store.delete("o-1", "col-A")


class TestListCells:
    def test_lists_all_cells_for_owner(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        store.put("o-1", "col-A", b"a")
        store.put("o-1", "col-B", b"b")
        store.put("o-1", "col-C", b"c")
        # Different owner — must not appear.
        store.put("o-2", "col-A", b"d")

        cols = sorted(store.list_cells("o-1"))
        assert cols == ["col-A", "col-B", "col-C"]

    def test_unknown_owner_returns_empty(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        store.put("o-1", "col-A", b"x")
        assert store.list_cells("ghost") == []

    def test_skips_non_cell_keys(self):
        client = _FakeS3Client()
        # Stray object inside the owner prefix that isn't a cell.
        client.objects[("b", "mantle-cells/o-1/README.txt")] = b"docs"
        store = S3CellStore(client, bucket="b")
        store.put("o-1", "col-A", b"a")
        assert store.list_cells("o-1") == ["col-A"]

    def test_skips_keys_outside_owner_prefix(self):
        client = _FakeS3Client()
        # Bucket has unrelated keys at root.
        client.objects[("b", "other/o-1/col-A.cell")] = b"junk"
        store = S3CellStore(client, bucket="b")
        store.put("o-1", "col-A", b"a")
        assert store.list_cells("o-1") == ["col-A"]

    def test_paginator_path_is_used(self):
        store = S3CellStore(_FakeS3Client(), bucket="b")
        for i in range(5):
            store.put("o-1", f"col-{i}", b"x")
        # Paginator code path is exercised whenever the client exposes
        # get_paginator (our fake does).
        cols = sorted(store.list_cells("o-1"))
        assert cols == [f"col-{i}" for i in range(5)]

    def test_falls_back_when_paginator_missing(self):
        class _NoPaginator(_FakeS3Client):
            get_paginator = None  # type: ignore[assignment]

        store = S3CellStore(_NoPaginator(), bucket="b")
        store.put("o-1", "col-A", b"a")
        store.put("o-1", "col-B", b"b")
        assert sorted(store.list_cells("o-1")) == ["col-A", "col-B"]


class TestNotFoundDetection:
    def test_get_swallows_no_such_key(self):
        # Arrange a client whose get_object raises a non-_NoSuchKey
        # exception that is shaped like a boto3 ClientError(NoSuchKey).
        class _ClientErrorLike(Exception):
            def __init__(self):
                super().__init__()
                self.response = {"Error": {"Code": "NoSuchKey"}}

        class _Boom(_FakeS3Client):
            def get_object(self, **_):
                raise _ClientErrorLike()

        store = S3CellStore(_Boom(), bucket="b")
        assert store.get("o-1", "col-A") is None

    def test_get_propagates_unrelated_errors(self):
        class _Boom(_FakeS3Client):
            def get_object(self, **_):
                raise RuntimeError("network exploded")

        store = S3CellStore(_Boom(), bucket="b")
        with pytest.raises(RuntimeError):
            store.get("o-1", "col-A")
