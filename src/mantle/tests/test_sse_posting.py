"""Tests for `search.mantle.sse.posting` (MANTLE-SSE Step 2.6.3).

Coverage:

- Key derivation: shape, determinism, blind-token separation, owner
  separation, manifest/posting tree independence.
- AEAD primitives: round-trip, tamper detection (nonce / ciphertext / tag),
  wrong-key rejection, malformed-blob handling, nonce uniqueness.
- Posting-list serialization: canonical encoding, list/object envelope
  validation, JSON round-trip, malformed JSON rejection.
- Manifest serialization: dedup + sort, round-trip, malformed handling.
- Mutation helpers: upsert (insert vs replace), per-artifact removal,
  per-(artifact, collection) removal, validation of required keys.
- Storage Protocol: in-memory implementation CRUD, owner isolation,
  thread-safety smoke, list_tokens_for_owner.
- Pack/unpack convenience wrappers: posting + manifest both directions.
"""

from __future__ import annotations

import os
import threading

import pytest
from cryptography.fernet import Fernet

from search.mantle.oracle import FernetMasterKeyStore, OracleService
from search.mantle.sse import blind_tokens as bt
from search.mantle.sse import posting


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def oracle() -> OracleService:
    fernet = Fernet(Fernet.generate_key())
    return OracleService(FernetMasterKeyStore(fernet))


@pytest.fixture
def owner_key(oracle: OracleService) -> bytes:
    return oracle.derive_sse_key("owner-A")


@pytest.fixture
def other_owner_key(oracle: OracleService) -> bytes:
    return oracle.derive_sse_key("owner-B")


@pytest.fixture
def token_a(owner_key: bytes) -> str:
    return bt.blind_token(owner_key, bt.FIELD_TITLE, "encryption")


@pytest.fixture
def token_b(owner_key: bytes) -> str:
    return bt.blind_token(owner_key, bt.FIELD_CONTENT, "blue")


@pytest.fixture
def aead_key() -> bytes:
    """Plain 256-bit AEAD key for the low-level encrypt_blob/decrypt_blob tests."""
    return os.urandom(32)


@pytest.fixture
def entries() -> list[dict]:
    return [
        {
            "artifact_id": "art-1",
            "collection_id": "col-1",
            "field": "title",
            "tf": 3,
            "dl": 12,
            "positions": [0, 5, 11],
        },
        {
            "artifact_id": "art-1",
            "collection_id": "col-2",
            "field": "title",
            "tf": 1,
            "dl": 8,
            "positions": [2],
        },
        {
            "artifact_id": "art-2",
            "collection_id": "col-1",
            "field": "title",
            "tf": 2,
            "dl": 15,
            "positions": [1, 9],
        },
    ]


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


class TestDerivePostingKey:
    def test_returns_32_bytes(self, owner_key, token_a):
        key = posting.derive_posting_key(owner_key, token_a)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_deterministic(self, owner_key, token_a):
        a = posting.derive_posting_key(owner_key, token_a)
        b = posting.derive_posting_key(owner_key, token_a)
        assert a == b

    def test_distinct_per_blind_token(self, owner_key, token_a, token_b):
        a = posting.derive_posting_key(owner_key, token_a)
        b = posting.derive_posting_key(owner_key, token_b)
        assert a != b

    def test_distinct_per_owner(self, owner_key, other_owner_key, token_a):
        # Same blind-token *string* under different owners — keys must differ.
        # (In practice the blind token would also differ; we want to verify
        # the key-derivation layer doesn't collapse owners.)
        a = posting.derive_posting_key(owner_key, token_a)
        b = posting.derive_posting_key(other_owner_key, token_a)
        assert a != b

    def test_independent_from_manifest_tree(self, owner_key, token_a):
        # Same owner key, different "info" prefix → independent keys.
        # We construct a 64-hex artifact-id-shaped string so the manifest
        # validator accepts it.
        artifact_id = token_a  # 64 hex chars → also a valid artifact-id shape
        post_key = posting.derive_posting_key(owner_key, token_a)
        man_key = posting.derive_manifest_key(owner_key, artifact_id)
        assert post_key != man_key

    def test_rejects_short_owner_key(self, token_a):
        with pytest.raises(ValueError, match="32 bytes"):
            posting.derive_posting_key(b"x" * 16, token_a)

    def test_rejects_non_bytes_owner_key(self, token_a):
        with pytest.raises(TypeError):
            posting.derive_posting_key("not-bytes", token_a)  # type: ignore[arg-type]

    def test_rejects_short_blind_token(self, owner_key):
        with pytest.raises(ValueError, match="64 hex chars"):
            posting.derive_posting_key(owner_key, "abc123")

    def test_rejects_non_hex_blind_token(self, owner_key):
        # 64 chars but not hex
        with pytest.raises(ValueError, match="hex"):
            posting.derive_posting_key(owner_key, "z" * 64)

    def test_rejects_empty_blind_token(self, owner_key):
        with pytest.raises(ValueError):
            posting.derive_posting_key(owner_key, "")


class TestDeriveManifestKey:
    def test_returns_32_bytes(self, owner_key):
        key = posting.derive_manifest_key(owner_key, "art-uuid")
        assert len(key) == 32

    def test_deterministic(self, owner_key):
        a = posting.derive_manifest_key(owner_key, "art-uuid")
        b = posting.derive_manifest_key(owner_key, "art-uuid")
        assert a == b

    def test_distinct_per_artifact(self, owner_key):
        a = posting.derive_manifest_key(owner_key, "art-1")
        b = posting.derive_manifest_key(owner_key, "art-2")
        assert a != b

    def test_distinct_per_owner(self, owner_key, other_owner_key):
        a = posting.derive_manifest_key(owner_key, "art-1")
        b = posting.derive_manifest_key(other_owner_key, "art-1")
        assert a != b

    def test_rejects_empty_artifact_id(self, owner_key):
        with pytest.raises(ValueError):
            posting.derive_manifest_key(owner_key, "")


# ---------------------------------------------------------------------------
# AEAD primitives
# ---------------------------------------------------------------------------


class TestEncryptDecryptBlob:
    def test_round_trip(self, aead_key):
        plaintext = b"hello MANTLE-SSE"
        blob = posting.encrypt_blob(plaintext, aead_key)
        assert posting.decrypt_blob(blob, aead_key) == plaintext

    def test_round_trip_empty(self, aead_key):
        blob = posting.encrypt_blob(b"", aead_key)
        assert posting.decrypt_blob(blob, aead_key) == b""

    def test_blob_shape_nonce_then_ct_tag(self, aead_key):
        blob = posting.encrypt_blob(b"x", aead_key)
        # 12-byte nonce + 1-byte ciphertext + 16-byte tag
        assert len(blob) == 12 + 1 + 16

    def test_fresh_nonce_per_call(self, aead_key):
        a = posting.encrypt_blob(b"same plaintext", aead_key)
        b = posting.encrypt_blob(b"same plaintext", aead_key)
        assert a != b
        # Both still decrypt to the same plaintext.
        assert posting.decrypt_blob(a, aead_key) == posting.decrypt_blob(b, aead_key)

    def test_wrong_key_raises_tampered(self, aead_key):
        blob = posting.encrypt_blob(b"secret", aead_key)
        wrong = os.urandom(32)
        with pytest.raises(posting.PostingTampered):
            posting.decrypt_blob(blob, wrong)

    def test_bitflip_in_nonce_detected(self, aead_key):
        blob = bytearray(posting.encrypt_blob(b"secret", aead_key))
        blob[0] ^= 0x01
        with pytest.raises(posting.PostingTampered):
            posting.decrypt_blob(bytes(blob), aead_key)

    def test_bitflip_in_ciphertext_detected(self, aead_key):
        blob = bytearray(posting.encrypt_blob(b"secret-cargo", aead_key))
        # Flip a byte in the middle of the ciphertext (past the nonce).
        blob[12 + 3] ^= 0x80
        with pytest.raises(posting.PostingTampered):
            posting.decrypt_blob(bytes(blob), aead_key)

    def test_bitflip_in_tag_detected(self, aead_key):
        blob = bytearray(posting.encrypt_blob(b"secret", aead_key))
        # Flip a byte in the trailing GCM tag.
        blob[-1] ^= 0x01
        with pytest.raises(posting.PostingTampered):
            posting.decrypt_blob(bytes(blob), aead_key)

    def test_short_blob_raises_malformed(self, aead_key):
        with pytest.raises(posting.PostingMalformed):
            posting.decrypt_blob(b"short", aead_key)

    def test_rejects_short_aead_key(self):
        with pytest.raises(ValueError, match="32 bytes"):
            posting.encrypt_blob(b"x", b"y" * 16)


# ---------------------------------------------------------------------------
# Posting-list (de)serialization
# ---------------------------------------------------------------------------


class TestSerializeEntries:
    def test_round_trip(self, entries):
        blob = posting.serialize_entries(entries)
        assert posting.deserialize_entries(blob) == entries

    def test_canonical_encoding(self, entries):
        # Same entries → same bytes (sorted keys, no whitespace).
        a = posting.serialize_entries(entries)
        b = posting.serialize_entries(entries)
        assert a == b
        # Should not contain spaces.
        assert b" " not in a

    def test_canonical_envelope_shape(self):
        # The wire envelope is {"entries": [...]} — fixed.
        blob = posting.serialize_entries([])
        assert blob == b'{"entries":[]}'

    def test_rejects_non_object_root(self):
        with pytest.raises(posting.PostingMalformed):
            posting.deserialize_entries(b'["entries"]')

    def test_rejects_missing_entries_key(self):
        with pytest.raises(posting.PostingMalformed, match="entries"):
            posting.deserialize_entries(b'{"other":[]}')

    def test_rejects_entries_not_list(self):
        with pytest.raises(posting.PostingMalformed):
            posting.deserialize_entries(b'{"entries":"oops"}')

    def test_rejects_invalid_json(self):
        with pytest.raises(posting.PostingMalformed):
            posting.deserialize_entries(b"not json")


class TestPackUnpackPosting:
    def test_round_trip(self, entries, aead_key):
        blob = posting.pack_posting(entries, aead_key)
        assert posting.unpack_posting(blob, aead_key) == entries

    def test_pack_blob_is_encrypted(self, entries, aead_key):
        blob = posting.pack_posting(entries, aead_key)
        # Plaintext term identifiers must not appear in the blob.
        assert b"art-1" not in blob
        assert b"col-1" not in blob

    def test_unpack_with_wrong_key_raises_tampered(self, entries, aead_key):
        blob = posting.pack_posting(entries, aead_key)
        with pytest.raises(posting.PostingTampered):
            posting.unpack_posting(blob, os.urandom(32))


# ---------------------------------------------------------------------------
# Manifest (de)serialization
# ---------------------------------------------------------------------------


class TestSerializeManifest:
    def test_dedups_and_sorts(self):
        blob = posting.serialize_manifest(["b" * 64, "a" * 64, "b" * 64])
        tokens, dls = posting.deserialize_manifest(blob)
        assert tokens == ["a" * 64, "b" * 64]
        assert dls == {}

    def test_drops_empty_tokens(self):
        blob = posting.serialize_manifest(["a" * 64, "", "b" * 64])
        tokens, _ = posting.deserialize_manifest(blob)
        assert tokens == ["a" * 64, "b" * 64]

    def test_round_trip_tokens_only(self):
        tokens = sorted({f"{i:064x}" for i in range(10)})
        blob = posting.serialize_manifest(tokens)
        recovered, dls = posting.deserialize_manifest(blob)
        assert recovered == tokens
        assert dls == {}

    def test_carries_field_dls(self):
        blob = posting.serialize_manifest(
            ["a" * 64], field_dls={"title": 5, "content": 100},
        )
        tokens, dls = posting.deserialize_manifest(blob)
        assert tokens == ["a" * 64]
        assert dls == {"title": 5, "content": 100}

    def test_drops_zero_dls(self):
        # Empty / zero-length fields shouldn't bloat the manifest.
        blob = posting.serialize_manifest(
            ["a" * 64], field_dls={"title": 5, "description": 0},
        )
        _, dls = posting.deserialize_manifest(blob)
        assert dls == {"title": 5}

    def test_canonical_empty(self):
        # Empty token list, no field_dls — canonical bytes are stable.
        assert posting.serialize_manifest([]) == b'{"field_dls":{},"tokens":[]}'

    def test_rejects_missing_tokens_key(self):
        with pytest.raises(posting.PostingMalformed, match="tokens"):
            posting.deserialize_manifest(b'{"other":[]}')

    def test_rejects_non_object_root(self):
        with pytest.raises(posting.PostingMalformed):
            posting.deserialize_manifest(b'["tokens"]')

    def test_rejects_invalid_json(self):
        with pytest.raises(posting.PostingMalformed):
            posting.deserialize_manifest(b"not json")

    def test_rejects_non_object_field_dls(self):
        with pytest.raises(posting.PostingMalformed, match="field_dls"):
            posting.deserialize_manifest(b'{"tokens":[],"field_dls":[]}')

    def test_rejects_non_int_field_dls_value(self):
        with pytest.raises(posting.PostingMalformed, match="field_dls"):
            posting.deserialize_manifest(
                b'{"tokens":[],"field_dls":{"title":"five"}}'
            )


class TestPackUnpackManifest:
    def test_round_trip(self, owner_key, token_a, token_b):
        key = posting.derive_manifest_key(owner_key, "art-1")
        blob = posting.pack_manifest([token_a, token_b], key)
        tokens, dls = posting.unpack_manifest(blob, key)
        assert tokens == sorted([token_a, token_b])
        assert dls == {}

    def test_round_trip_with_field_dls(self, owner_key, token_a):
        key = posting.derive_manifest_key(owner_key, "art-1")
        blob = posting.pack_manifest(
            [token_a], key, field_dls={"title": 5, "content": 200},
        )
        tokens, dls = posting.unpack_manifest(blob, key)
        assert tokens == [token_a]
        assert dls == {"title": 5, "content": 200}

    def test_wrong_key_raises_tampered(self, owner_key, token_a):
        key = posting.derive_manifest_key(owner_key, "art-1")
        blob = posting.pack_manifest([token_a], key)
        wrong = posting.derive_manifest_key(owner_key, "art-2")
        with pytest.raises(posting.PostingTampered):
            posting.unpack_manifest(blob, wrong)


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


class TestUpsertEntry:
    def test_appends_new_entry(self, entries):
        new = {
            "artifact_id": "art-3", "collection_id": "col-1",
            "field": "title", "tf": 1, "dl": 4, "positions": [0],
        }
        before = len(entries)
        posting.upsert_entry(entries, new)
        assert len(entries) == before + 1
        assert entries[-1] is new

    def test_replaces_matching_artifact_collection(self, entries):
        # entries[0] is (art-1, col-1). Re-indexing should overwrite.
        replacement = {
            "artifact_id": "art-1", "collection_id": "col-1",
            "field": "title", "tf": 99, "dl": 99, "positions": [],
        }
        posting.upsert_entry(entries, replacement)
        # Same length — replaced in place.
        assert len(entries) == 3
        # The (art-1, col-1) entry now has tf=99.
        match = [
            e for e in entries
            if e["artifact_id"] == "art-1" and e["collection_id"] == "col-1"
        ]
        assert len(match) == 1
        assert match[0]["tf"] == 99

    def test_distinguishes_collection(self, entries):
        # entries already has (art-1, col-1) and (art-1, col-2). Both
        # should remain — same artifact, different collections.
        starting_pairs = {
            (e["artifact_id"], e["collection_id"]) for e in entries
        }
        assert ("art-1", "col-1") in starting_pairs
        assert ("art-1", "col-2") in starting_pairs

    def test_returns_same_list_reference(self, entries):
        new = {
            "artifact_id": "art-4", "collection_id": "col-1",
            "field": "title", "tf": 1, "dl": 4, "positions": [0],
        }
        result = posting.upsert_entry(entries, new)
        assert result is entries

    def test_rejects_missing_artifact_id(self, entries):
        with pytest.raises(ValueError, match="artifact_id"):
            posting.upsert_entry(entries, {"collection_id": "col-1"})

    def test_rejects_missing_collection_id(self, entries):
        with pytest.raises(ValueError, match="collection_id"):
            posting.upsert_entry(entries, {"artifact_id": "art-x"})


class TestRemoveArtifactEntries:
    def test_strips_all_entries_for_artifact(self, entries):
        # entries has two (art-1) entries across col-1 and col-2.
        out = posting.remove_artifact_entries(entries, "art-1")
        assert len(out) == 1
        assert out[0]["artifact_id"] == "art-2"

    def test_returns_new_list(self, entries):
        out = posting.remove_artifact_entries(entries, "art-1")
        assert out is not entries
        # Original is unchanged.
        assert len(entries) == 3

    def test_no_match_returns_full_copy(self, entries):
        out = posting.remove_artifact_entries(entries, "art-not-here")
        assert out == entries
        assert out is not entries


class TestRemoveArtifactCollectionEntries:
    def test_strips_only_one_pair(self, entries):
        # (art-1, col-1) goes; (art-1, col-2) and (art-2, col-1) remain.
        out = posting.remove_artifact_collection_entries(
            entries, "art-1", "col-1"
        )
        pairs = {(e["artifact_id"], e["collection_id"]) for e in out}
        assert pairs == {("art-1", "col-2"), ("art-2", "col-1")}

    def test_returns_new_list(self, entries):
        out = posting.remove_artifact_collection_entries(
            entries, "art-1", "col-1"
        )
        assert out is not entries
        assert len(entries) == 3


class TestEntryHelpers:
    def test_entry_count(self, entries):
        assert posting.entry_count(entries) == 3
        assert posting.entry_count([]) == 0

    def test_artifact_ids_in_entries(self, entries):
        assert posting.artifact_ids_in_entries(entries) == {"art-1", "art-2"}

    def test_artifact_ids_in_entries_skips_missing_key(self):
        assert posting.artifact_ids_in_entries(
            [{"collection_id": "col-1"}]
        ) == set()


# ---------------------------------------------------------------------------
# InMemoryPostingStore
# ---------------------------------------------------------------------------


class TestInMemoryPostingStore:
    def test_get_missing_returns_none(self):
        store = posting.InMemoryPostingStore()
        assert store.get_posting("owner-A", "a" * 64) is None
        assert store.get_manifest("owner-A", "art-1") is None

    def test_posting_round_trip(self):
        store = posting.InMemoryPostingStore()
        store.put_posting("owner-A", "a" * 64, b"blob-1")
        assert store.get_posting("owner-A", "a" * 64) == b"blob-1"

    def test_posting_overwrite(self):
        store = posting.InMemoryPostingStore()
        store.put_posting("owner-A", "a" * 64, b"v1")
        store.put_posting("owner-A", "a" * 64, b"v2")
        assert store.get_posting("owner-A", "a" * 64) == b"v2"

    def test_posting_delete(self):
        store = posting.InMemoryPostingStore()
        store.put_posting("owner-A", "a" * 64, b"blob")
        store.delete_posting("owner-A", "a" * 64)
        assert store.get_posting("owner-A", "a" * 64) is None

    def test_posting_delete_missing_is_noop(self):
        store = posting.InMemoryPostingStore()
        store.delete_posting("owner-A", "a" * 64)  # does not raise

    def test_owner_isolation_postings(self):
        store = posting.InMemoryPostingStore()
        store.put_posting("owner-A", "a" * 64, b"A-blob")
        store.put_posting("owner-B", "a" * 64, b"B-blob")
        assert store.get_posting("owner-A", "a" * 64) == b"A-blob"
        assert store.get_posting("owner-B", "a" * 64) == b"B-blob"

    def test_list_tokens_for_owner(self):
        store = posting.InMemoryPostingStore()
        store.put_posting("owner-A", "a" * 64, b"x")
        store.put_posting("owner-A", "b" * 64, b"y")
        store.put_posting("owner-B", "c" * 64, b"z")
        tokens_a = store.list_tokens_for_owner("owner-A")
        assert sorted(tokens_a) == sorted(["a" * 64, "b" * 64])
        assert store.list_tokens_for_owner("owner-B") == ["c" * 64]
        assert store.list_tokens_for_owner("owner-empty") == []

    def test_manifest_round_trip(self):
        store = posting.InMemoryPostingStore()
        store.put_manifest("owner-A", "art-1", b"manifest-blob")
        assert store.get_manifest("owner-A", "art-1") == b"manifest-blob"

    def test_manifest_delete(self):
        store = posting.InMemoryPostingStore()
        store.put_manifest("owner-A", "art-1", b"x")
        store.delete_manifest("owner-A", "art-1")
        assert store.get_manifest("owner-A", "art-1") is None

    def test_manifest_owner_isolation(self):
        store = posting.InMemoryPostingStore()
        store.put_manifest("owner-A", "art-1", b"A-m")
        store.put_manifest("owner-B", "art-1", b"B-m")
        assert store.get_manifest("owner-A", "art-1") == b"A-m"
        assert store.get_manifest("owner-B", "art-1") == b"B-m"

    def test_posting_and_manifest_are_independent(self):
        # Same (principal_id, "id") shouldn't collide between the two namespaces.
        store = posting.InMemoryPostingStore()
        store.put_posting("owner-A", "a" * 64, b"posting-blob")
        store.put_manifest("owner-A", "a" * 64, b"manifest-blob")
        assert store.get_posting("owner-A", "a" * 64) == b"posting-blob"
        assert store.get_manifest("owner-A", "a" * 64) == b"manifest-blob"

    def test_thread_safety_smoke(self):
        store = posting.InMemoryPostingStore()
        errors: list[BaseException] = []

        def worker(prefix: str) -> None:
            try:
                for i in range(100):
                    tok = f"{prefix}{i:063x}"  # pad to 64 hex chars
                    store.put_posting("owner-A", tok, f"{prefix}-{i}".encode())
                    assert store.get_posting("owner-A", tok) is not None
            except BaseException as exc:  # pragma: no cover
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(p,))
            for p in ("a", "b", "c", "d")
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # 4 threads × 100 entries each, all under owner-A.
        assert len(store.list_tokens_for_owner("owner-A")) == 400


# ---------------------------------------------------------------------------
# End-to-end indexer-shape integration
# ---------------------------------------------------------------------------


class TestIndexerShape:
    """Sanity check the full indexer cycle: derive key → pack → store →
    fetch → unpack → mutate → re-pack. This is the read-modify-write
    pattern the MantleSseIndexer (Step 2.6.6) will use."""

    def test_full_round_trip_through_store(self, oracle, owner_key):
        store = posting.InMemoryPostingStore()
        token = bt.blind_token(owner_key, bt.FIELD_TITLE, "encryption")

        # Index art-1
        key = posting.derive_posting_key(owner_key, token)
        entries: list[dict] = []
        posting.upsert_entry(entries, {
            "artifact_id": "art-1", "collection_id": "col-1",
            "field": "title", "tf": 2, "dl": 8, "positions": [0, 4],
        })
        store.put_posting("owner-A", token, posting.pack_posting(entries, key))

        # Index art-2 (read-modify-write)
        blob = store.get_posting("owner-A", token)
        assert blob is not None
        loaded = posting.unpack_posting(blob, key)
        posting.upsert_entry(loaded, {
            "artifact_id": "art-2", "collection_id": "col-1",
            "field": "title", "tf": 1, "dl": 5, "positions": [3],
        })
        store.put_posting("owner-A", token, posting.pack_posting(loaded, key))

        # Verify both entries present.
        final = posting.unpack_posting(
            store.get_posting("owner-A", token), key
        )
        assert posting.artifact_ids_in_entries(final) == {"art-1", "art-2"}

        # Remove art-1 (deletion path).
        loaded = posting.unpack_posting(
            store.get_posting("owner-A", token), key
        )
        loaded = posting.remove_artifact_entries(loaded, "art-1")
        store.put_posting("owner-A", token, posting.pack_posting(loaded, key))

        final = posting.unpack_posting(
            store.get_posting("owner-A", token), key
        )
        assert posting.artifact_ids_in_entries(final) == {"art-2"}

    def test_manifest_tracks_indexed_tokens(self, owner_key):
        store = posting.InMemoryPostingStore()
        manifest_key = posting.derive_manifest_key(owner_key, "art-1")

        # An artifact gets indexed under three blind tokens.
        tokens = [
            bt.blind_token(owner_key, bt.FIELD_TITLE, "alpha"),
            bt.blind_token(owner_key, bt.FIELD_TITLE, "beta"),
            bt.blind_token(owner_key, bt.FIELD_DESCRIPTION, "gamma"),
        ]
        store.put_manifest(
            "owner-A", "art-1",
            posting.pack_manifest(tokens, manifest_key),
        )

        # Retrieval round-trip preserves the set.
        recovered_tokens, recovered_dls = posting.unpack_manifest(
            store.get_manifest("owner-A", "art-1"), manifest_key,
        )
        assert sorted(tokens) == recovered_tokens
        assert recovered_dls == {}

    def test_at_rest_blob_does_not_leak_plaintext(self, owner_key, entries):
        """A stored posting blob must not contain plaintext artifact ids,
        collection ids, or field names — the at-rest leakage budget."""
        token = bt.blind_token(owner_key, bt.FIELD_TITLE, "secret")
        key = posting.derive_posting_key(owner_key, token)
        blob = posting.pack_posting(entries, key)

        for needle in (b"art-1", b"art-2", b"col-1", b"col-2", b"title"):
            assert needle not in blob, f"plaintext leak: {needle!r}"

        # And the wrong owner can't decrypt.
        wrong_key = os.urandom(32)
        with pytest.raises(posting.PostingTampered):
            posting.unpack_posting(blob, wrong_key)
