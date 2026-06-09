"""Tests for the S3-backed SSE PostingStore + StatsStore adapters
(MANTLE-SSE Step 2.6.9 production wiring).

Reuses the fake S3 client pattern from :file:`test_s3_cell_store.py` to
keep this test file dependency-free (no boto3 / moto).

Coverage:

- S3PostingStore: posting + manifest get/put/delete round-trip, missing
  key returns None, delete missing is no-op, list_tokens_for_owner
  parses keys correctly with paginator and without, key construction
  (prefix + owner + namespace).
- S3StatsStore: get/put/delete round-trip, missing key handling,
  per-owner key isolation.
- Round-trip with the SSE crypto: indexer-shape end-to-end
  (encrypt → S3 → decrypt) verifies the adapters preserve the wire
  format byte-for-byte.
- Bucket / prefix validation.
"""

from __future__ import annotations

from typing import Optional

import pytest
from cryptography.fernet import Fernet

from search.mantle.oracle import FernetMasterKeyStore, OracleService
from search.mantle.sse import (
    blind_tokens as bt,
    posting,
    stats as stats_mod,
)
from search.mantle.sse.s3_stores import S3PostingStore, S3StatsStore


# ---------------------------------------------------------------------------
# Fake S3 client (mirrors test_s3_cell_store)
# ---------------------------------------------------------------------------


class _NoSuchKey(Exception):
    def __init__(self) -> None:
        super().__init__("NoSuchKey")
        self.response = {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}


class _FakePaginator:
    def __init__(self, client: "_FakeS3Client", method: str) -> None:
        self._client = client
        self._method = method

    def paginate(self, **kwargs):
        yield self._client.list_objects_v2(**kwargs)


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

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

            def read(self) -> bytes:
                return self._b

            def close(self) -> None:
                pass

        return {"Body": _Body(data)}

    def delete_object(self, *, Bucket: str, Key: str) -> dict:
        self.objects.pop((Bucket, Key), None)
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

    def list_objects_v2(self, *, Bucket: str, Prefix: str = "") -> dict:
        contents = [
            {"Key": k} for (b, k) in self.objects.keys()
            if b == Bucket and k.startswith(Prefix)
        ]
        return {"Contents": contents}

    def get_paginator(self, method: str) -> "_FakePaginator":
        return _FakePaginator(self, method)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def s3() -> _FakeS3Client:
    return _FakeS3Client()


@pytest.fixture
def posting_store(s3: _FakeS3Client) -> S3PostingStore:
    return S3PostingStore(s3, bucket="agience", prefix="mantle-sse")


@pytest.fixture
def stats_store(s3: _FakeS3Client) -> S3StatsStore:
    return S3StatsStore(s3, bucket="agience", prefix="mantle-sse")


@pytest.fixture
def oracle() -> OracleService:
    fernet = Fernet(Fernet.generate_key())
    return OracleService(FernetMasterKeyStore(fernet))


@pytest.fixture
def owner_key(oracle: OracleService) -> bytes:
    return oracle.derive_sse_key("owner-A")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestConstructorValidation:
    def test_posting_store_requires_bucket(self):
        with pytest.raises(ValueError, match="bucket"):
            S3PostingStore(_FakeS3Client(), bucket="")

    def test_stats_store_requires_bucket(self):
        with pytest.raises(ValueError, match="bucket"):
            S3StatsStore(_FakeS3Client(), bucket="")


# ---------------------------------------------------------------------------
# S3PostingStore — postings
# ---------------------------------------------------------------------------


class TestS3PostingStorePostings:
    def test_get_missing_returns_none(self, posting_store):
        assert posting_store.get_posting("owner-A", "a" * 64) is None

    def test_put_get_round_trip(self, posting_store):
        posting_store.put_posting("owner-A", "a" * 64, b"blob-data")
        assert posting_store.get_posting("owner-A", "a" * 64) == b"blob-data"

    def test_put_overwrite(self, posting_store):
        posting_store.put_posting("owner-A", "a" * 64, b"v1")
        posting_store.put_posting("owner-A", "a" * 64, b"v2")
        assert posting_store.get_posting("owner-A", "a" * 64) == b"v2"

    def test_delete(self, posting_store):
        posting_store.put_posting("owner-A", "a" * 64, b"x")
        posting_store.delete_posting("owner-A", "a" * 64)
        assert posting_store.get_posting("owner-A", "a" * 64) is None

    def test_delete_missing_is_noop(self, posting_store):
        posting_store.delete_posting("owner-A", "a" * 64)  # no error

    def test_owner_isolation(self, posting_store):
        posting_store.put_posting("owner-A", "a" * 64, b"A")
        posting_store.put_posting("owner-B", "a" * 64, b"B")
        assert posting_store.get_posting("owner-A", "a" * 64) == b"A"
        assert posting_store.get_posting("owner-B", "a" * 64) == b"B"

    def test_posting_key_layout(self, s3, posting_store):
        posting_store.put_posting("owner-A", "a" * 64, b"x")
        # Key format: {prefix}/{principal_id}/sse/posting/{token}.enc
        expected = f"mantle-sse/owner-A/sse/posting/{'a' * 64}.enc"
        assert ("agience", expected) in s3.objects

    def test_list_tokens_paginated(self, posting_store):
        toks = [f"{i:064x}" for i in range(5)]
        for t in toks:
            posting_store.put_posting("owner-A", t, b"x")
        # Mix in a different owner.
        posting_store.put_posting("owner-B", "f" * 64, b"y")
        listed = posting_store.list_tokens_for_owner("owner-A")
        assert sorted(listed) == sorted(toks)

    def test_list_tokens_empty_for_unknown_owner(self, posting_store):
        assert posting_store.list_tokens_for_owner("owner-empty") == []

    def test_list_tokens_only_returns_enc_keys(self, s3, posting_store):
        posting_store.put_posting("owner-A", "a" * 64, b"valid")
        # Inject a stray non-.enc key under the owner's prefix.
        s3.objects[("agience", "mantle-sse/owner-A/sse/posting/garbage.txt")] = b"x"
        # The stray shouldn't show up.
        listed = posting_store.list_tokens_for_owner("owner-A")
        assert listed == ["a" * 64]


# ---------------------------------------------------------------------------
# S3PostingStore — manifests
# ---------------------------------------------------------------------------


class TestS3PostingStoreManifests:
    def test_get_missing_returns_none(self, posting_store):
        assert posting_store.get_manifest("owner-A", "art-1") is None

    def test_round_trip(self, posting_store):
        posting_store.put_manifest("owner-A", "art-1", b"manifest-blob")
        assert posting_store.get_manifest("owner-A", "art-1") == b"manifest-blob"

    def test_delete(self, posting_store):
        posting_store.put_manifest("owner-A", "art-1", b"x")
        posting_store.delete_manifest("owner-A", "art-1")
        assert posting_store.get_manifest("owner-A", "art-1") is None

    def test_owner_isolation(self, posting_store):
        posting_store.put_manifest("owner-A", "art-1", b"A")
        posting_store.put_manifest("owner-B", "art-1", b"B")
        assert posting_store.get_manifest("owner-A", "art-1") == b"A"
        assert posting_store.get_manifest("owner-B", "art-1") == b"B"

    def test_postings_and_manifests_are_independent(self, posting_store):
        # Same id-shape under both namespaces — no collision.
        posting_store.put_posting("owner-A", "a" * 64, b"posting")
        posting_store.put_manifest("owner-A", "a" * 64, b"manifest")
        assert posting_store.get_posting("owner-A", "a" * 64) == b"posting"
        assert posting_store.get_manifest("owner-A", "a" * 64) == b"manifest"

    def test_manifest_key_layout(self, s3, posting_store):
        posting_store.put_manifest("owner-A", "art-1", b"x")
        expected = "mantle-sse/owner-A/sse/manifests/art-1.enc"
        assert ("agience", expected) in s3.objects


# ---------------------------------------------------------------------------
# S3StatsStore
# ---------------------------------------------------------------------------


class TestS3StatsStore:
    def test_get_missing_returns_none(self, stats_store):
        assert stats_store.get("owner-A") is None

    def test_round_trip(self, stats_store):
        stats_store.put("owner-A", b"blob")
        assert stats_store.get("owner-A") == b"blob"

    def test_overwrite(self, stats_store):
        stats_store.put("owner-A", b"v1")
        stats_store.put("owner-A", b"v2")
        assert stats_store.get("owner-A") == b"v2"

    def test_delete(self, stats_store):
        stats_store.put("owner-A", b"x")
        stats_store.delete("owner-A")
        assert stats_store.get("owner-A") is None

    def test_delete_missing_is_noop(self, stats_store):
        stats_store.delete("owner-A")  # no error

    def test_owner_isolation(self, stats_store):
        stats_store.put("owner-A", b"A")
        stats_store.put("owner-B", b"B")
        assert stats_store.get("owner-A") == b"A"
        assert stats_store.get("owner-B") == b"B"

    def test_stats_key_layout(self, s3, stats_store):
        stats_store.put("owner-A", b"x")
        assert ("agience", "mantle-sse/owner-A/sse/stats.enc") in s3.objects


# ---------------------------------------------------------------------------
# End-to-end with crypto (encrypted blob round-trip through S3)
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_posting_through_s3(self, posting_store, owner_key):
        token = bt.blind_token(owner_key, bt.FIELD_TITLE, "encryption")
        key = posting.derive_posting_key(owner_key, token)

        entries = [{
            "artifact_id": "art-1", "collection_id": "col-1",
            "field": "title", "tf": 2, "dl": 6, "positions": [0, 4],
        }]
        blob = posting.pack_posting(entries, key)
        posting_store.put_posting("owner-A", token, blob)

        # Round-trip through S3 → identical entries.
        recovered_blob = posting_store.get_posting("owner-A", token)
        assert recovered_blob == blob
        recovered = posting.unpack_posting(recovered_blob, key)
        assert recovered == entries

    def test_manifest_through_s3(self, posting_store, owner_key):
        manifest_key = posting.derive_manifest_key(owner_key, "art-1")
        tokens = [
            bt.blind_token(owner_key, bt.FIELD_TITLE, "alpha"),
            bt.blind_token(owner_key, bt.FIELD_TITLE, "beta"),
        ]
        blob = posting.pack_manifest(
            tokens, manifest_key, field_dls={"title": 2},
        )
        posting_store.put_manifest("owner-A", "art-1", blob)

        recovered_blob = posting_store.get_manifest("owner-A", "art-1")
        assert recovered_blob == blob
        rec_tokens, rec_dls = posting.unpack_manifest(recovered_blob, manifest_key)
        assert sorted(tokens) == rec_tokens
        assert rec_dls == {"title": 2}

    def test_stats_through_s3(self, stats_store, owner_key):
        skey = stats_mod.derive_stats_key(owner_key)
        s = stats_mod.Stats(
            doc_count=3,
            field_doc_count={"title": 3},
            field_total_dl={"title": 19},
            df={"a" * 64: 2},
        )
        blob = stats_mod.pack_stats(s, skey)
        stats_store.put("owner-A", blob)

        recovered_blob = stats_store.get("owner-A")
        assert recovered_blob == blob
        recovered = stats_mod.unpack_stats(recovered_blob, skey)
        assert recovered == s
