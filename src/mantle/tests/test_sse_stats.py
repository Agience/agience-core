"""Tests for `search.mantle.sse.stats` (MANTLE-SSE Step 2.6.4).

Coverage:

- Key derivation (derive_stats_key): shape, determinism, per-owner
  separation, independence from posting / manifest key trees.
- Stats dataclass: empty defaults; average_dl computation including the
  zero-doc / missing-field edge case.
- Serialization: canonical JSON round-trip, totals-not-floats wire format,
  malformed-blob handling.
- pack_stats / unpack_stats: round-trip via AEAD; wrong-key rejection.
- add_document / remove_document: counter math, dedup-required df, zero-dl
  fields skipped, removal clamps at zero, df keys with reach-zero count
  dropped.
- Sequential add/remove/add invariants (zero-out → re-add yields
  identical state).
- InMemoryStatsStore: round-trip, owner isolation, delete, missing reads.
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from search.mantle.oracle import FernetMasterKeyStore, OracleService
from search.mantle.sse import blind_tokens as bt
from search.mantle.sse import posting, stats


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
def stats_key(owner_key: bytes) -> bytes:
    return stats.derive_stats_key(owner_key)


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


class TestDeriveStatsKey:
    def test_returns_32_bytes(self, owner_key):
        key = stats.derive_stats_key(owner_key)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_deterministic(self, owner_key):
        a = stats.derive_stats_key(owner_key)
        b = stats.derive_stats_key(owner_key)
        assert a == b

    def test_distinct_per_owner(self, owner_key, other_owner_key):
        a = stats.derive_stats_key(owner_key)
        b = stats.derive_stats_key(other_owner_key)
        assert a != b

    def test_independent_from_posting_tree(self, owner_key):
        """Stats and posting keys must be cryptographically independent —
        same owner SSE key but different HKDF info."""
        token = bt.blind_token(owner_key, bt.FIELD_TITLE, "anything")
        stats_k = stats.derive_stats_key(owner_key)
        post_k = posting.derive_posting_key(owner_key, token)
        assert stats_k != post_k

    def test_independent_from_manifest_tree(self, owner_key):
        # 64-hex artifact id (any well-formed string is fine for derivation)
        artifact_id = "a" * 64
        stats_k = stats.derive_stats_key(owner_key)
        man_k = posting.derive_manifest_key(owner_key, artifact_id)
        assert stats_k != man_k

    def test_rejects_short_owner_key(self):
        with pytest.raises(ValueError, match="32 bytes"):
            stats.derive_stats_key(b"x" * 16)

    def test_rejects_non_bytes_owner_key(self):
        with pytest.raises(TypeError):
            stats.derive_stats_key("not-bytes")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Stats dataclass
# ---------------------------------------------------------------------------


class TestStats:
    def test_empty_defaults(self):
        s = stats.empty_stats()
        assert s.doc_count == 0
        assert s.field_doc_count == {}
        assert s.field_total_dl == {}
        assert s.df == {}

    def test_average_dl_zero_when_field_absent(self):
        s = stats.empty_stats()
        assert s.average_dl("title") == 0.0

    def test_average_dl_zero_when_zero_doc_count(self):
        s = stats.Stats(field_doc_count={"title": 0}, field_total_dl={"title": 0})
        assert s.average_dl("title") == 0.0

    def test_average_dl_simple(self):
        s = stats.Stats(
            field_doc_count={"title": 4},
            field_total_dl={"title": 24},
        )
        assert s.average_dl("title") == 6.0

    def test_average_dl_all_returns_per_field(self):
        s = stats.Stats(
            field_doc_count={"title": 4, "content": 4},
            field_total_dl={"title": 24, "content": 1928},
        )
        assert s.average_dl_all() == {"title": 6.0, "content": 482.0}

    def test_df_for_missing_returns_zero(self):
        s = stats.empty_stats()
        assert s.df_for("a" * 64) == 0


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerializeStats:
    def test_round_trip_empty(self):
        blob = stats.serialize_stats(stats.empty_stats())
        assert stats.deserialize_stats(blob) == stats.empty_stats()

    def test_round_trip_populated(self):
        s = stats.Stats(
            doc_count=10,
            field_doc_count={"title": 10, "content": 9},
            field_total_dl={"title": 60, "content": 4500},
            df={"a" * 64: 3, "b" * 64: 7},
        )
        blob = stats.serialize_stats(s)
        recovered = stats.deserialize_stats(blob)
        assert recovered == s

    def test_canonical_encoding(self):
        s = stats.Stats(
            doc_count=2,
            field_doc_count={"title": 2},
            field_total_dl={"title": 8},
        )
        a = stats.serialize_stats(s)
        b = stats.serialize_stats(s)
        assert a == b
        assert b" " not in a

    def test_wire_format_stores_totals_not_floats(self):
        """The wire format must store integer running totals, not the
        derived ``avg_dl`` floats — guards against drift after many updates."""
        s = stats.Stats(
            doc_count=3,
            field_doc_count={"title": 3},
            field_total_dl={"title": 19},  # avg = 6.333...
        )
        blob = stats.serialize_stats(s)
        # The stored numbers are integers — no float repr in JSON.
        assert b'"field_total_dl":{"title":19}' in blob
        assert b'"avg_dl"' not in blob

    def test_rejects_invalid_json(self):
        with pytest.raises(posting.PostingMalformed):
            stats.deserialize_stats(b"not json")

    def test_rejects_non_object_root(self):
        with pytest.raises(posting.PostingMalformed):
            stats.deserialize_stats(b"[]")

    def test_rejects_missing_field(self):
        with pytest.raises(posting.PostingMalformed):
            stats.deserialize_stats(b'{"doc_count": 1}')

    def test_rejects_non_int_doc_count(self):
        bad = b'{"doc_count":"hi","field_doc_count":{},"field_total_dl":{},"df":{}}'
        with pytest.raises(posting.PostingMalformed):
            stats.deserialize_stats(bad)


class TestPackUnpackStats:
    def test_round_trip(self, stats_key):
        s = stats.Stats(
            doc_count=3,
            field_doc_count={"title": 3},
            field_total_dl={"title": 19},
            df={"a" * 64: 2},
        )
        blob = stats.pack_stats(s, stats_key)
        recovered = stats.unpack_stats(blob, stats_key)
        assert recovered == s

    def test_at_rest_is_encrypted(self, stats_key):
        """Plaintext field names mustn't appear in the at-rest blob."""
        s = stats.Stats(
            doc_count=3,
            field_doc_count={"title": 3},
            field_total_dl={"title": 19},
            df={},
        )
        blob = stats.pack_stats(s, stats_key)
        for needle in (b"doc_count", b"title", b"field_doc_count"):
            assert needle not in blob, f"plaintext leak: {needle!r}"

    def test_wrong_key_raises_tampered(self, stats_key):
        s = stats.Stats(doc_count=1)
        blob = stats.pack_stats(s, stats_key)
        wrong = os.urandom(32)
        with pytest.raises(posting.PostingTampered):
            stats.unpack_stats(blob, wrong)

    def test_owner_isolation(self, owner_key, other_owner_key):
        """An owner-A blob can't be decrypted with owner-B's stats key."""
        a_key = stats.derive_stats_key(owner_key)
        b_key = stats.derive_stats_key(other_owner_key)
        blob = stats.pack_stats(stats.Stats(doc_count=42), a_key)
        with pytest.raises(posting.PostingTampered):
            stats.unpack_stats(blob, b_key)


# ---------------------------------------------------------------------------
# Mutation: add_document / remove_document
# ---------------------------------------------------------------------------


class TestAddDocument:
    def test_increments_doc_count(self):
        s = stats.empty_stats()
        stats.add_document(s, field_dls={"title": 5}, blind_tokens=[])
        assert s.doc_count == 1

    def test_field_totals_accumulate(self):
        s = stats.empty_stats()
        stats.add_document(
            s, field_dls={"title": 5, "content": 200}, blind_tokens=[]
        )
        stats.add_document(
            s, field_dls={"title": 7, "content": 180}, blind_tokens=[]
        )
        assert s.field_doc_count == {"title": 2, "content": 2}
        assert s.field_total_dl == {"title": 12, "content": 380}
        assert s.average_dl("title") == 6.0
        assert s.average_dl("content") == 190.0

    def test_zero_dl_field_skipped(self):
        s = stats.empty_stats()
        stats.add_document(
            s, field_dls={"title": 5, "description": 0}, blind_tokens=[]
        )
        assert "description" not in s.field_doc_count
        assert "description" not in s.field_total_dl
        assert s.field_doc_count["title"] == 1

    def test_negative_dl_field_skipped(self):
        s = stats.empty_stats()
        stats.add_document(s, field_dls={"title": -3}, blind_tokens=[])
        assert "title" not in s.field_doc_count

    def test_df_increments_per_unique_token(self):
        s = stats.empty_stats()
        stats.add_document(
            s, field_dls={"title": 3},
            blind_tokens={"a" * 64, "b" * 64},
        )
        assert s.df == {"a" * 64: 1, "b" * 64: 1}

    def test_df_multi_doc(self):
        s = stats.empty_stats()
        stats.add_document(
            s, field_dls={"title": 3},
            blind_tokens={"a" * 64, "b" * 64},
        )
        stats.add_document(
            s, field_dls={"title": 4},
            blind_tokens={"a" * 64, "c" * 64},
        )
        assert s.df == {"a" * 64: 2, "b" * 64: 1, "c" * 64: 1}

    def test_empty_token_filtered(self):
        s = stats.empty_stats()
        stats.add_document(
            s, field_dls={"title": 3},
            blind_tokens={"a" * 64, ""},
        )
        assert s.df == {"a" * 64: 1}

    def test_returns_same_reference(self):
        s = stats.empty_stats()
        result = stats.add_document(s, field_dls={"title": 1}, blind_tokens=[])
        assert result is s


class TestRemoveDocument:
    def test_decrements_counters(self):
        s = stats.empty_stats()
        stats.add_document(s, field_dls={"title": 5}, blind_tokens={"a" * 64})
        stats.add_document(s, field_dls={"title": 7}, blind_tokens={"a" * 64})
        stats.remove_document(s, field_dls={"title": 5}, blind_tokens={"a" * 64})
        assert s.doc_count == 1
        assert s.field_doc_count == {"title": 1}
        assert s.field_total_dl == {"title": 7}
        assert s.df == {"a" * 64: 1}

    def test_removes_field_when_count_hits_zero(self):
        s = stats.empty_stats()
        stats.add_document(s, field_dls={"title": 5}, blind_tokens=[])
        stats.remove_document(s, field_dls={"title": 5}, blind_tokens=[])
        assert "title" not in s.field_doc_count
        assert "title" not in s.field_total_dl

    def test_drops_df_entry_when_zero(self):
        s = stats.empty_stats()
        stats.add_document(s, field_dls={"title": 1}, blind_tokens={"a" * 64})
        stats.remove_document(
            s, field_dls={"title": 1}, blind_tokens={"a" * 64}
        )
        assert "a" * 64 not in s.df

    def test_clamps_negative(self):
        """Removing more than was added doesn't drive counters negative."""
        s = stats.empty_stats()
        stats.remove_document(s, field_dls={"title": 5}, blind_tokens={"a" * 64})
        assert s.doc_count == 0
        assert s.field_doc_count == {}
        assert s.field_total_dl == {}
        assert s.df == {}

    def test_remove_unknown_token_is_noop(self):
        s = stats.empty_stats()
        stats.add_document(s, field_dls={"title": 5}, blind_tokens={"a" * 64})
        stats.remove_document(
            s, field_dls={"title": 5}, blind_tokens={"unknown" * 8 + "abcdefgh"},
        )
        # doc_count + field counters decremented, df["a"*64] still 1.
        assert s.doc_count == 0
        assert s.df == {"a" * 64: 1}

    def test_zero_dl_field_skipped_on_remove(self):
        s = stats.empty_stats()
        stats.add_document(s, field_dls={"title": 5}, blind_tokens=[])
        stats.remove_document(
            s, field_dls={"title": 5, "description": 0}, blind_tokens=[]
        )
        # "description" never tracked, no error raised.
        assert s.field_doc_count == {}


class TestAddRemoveInvariants:
    def test_add_then_remove_yields_empty(self):
        s = stats.empty_stats()
        stats.add_document(
            s, field_dls={"title": 6, "content": 100},
            blind_tokens={"a" * 64, "b" * 64},
        )
        stats.remove_document(
            s, field_dls={"title": 6, "content": 100},
            blind_tokens={"a" * 64, "b" * 64},
        )
        assert s == stats.empty_stats()

    def test_add_remove_add_yields_single_doc_state(self):
        """Round-trip should be idempotent: a doc removed and re-added
        produces the same state as adding once from empty."""
        a = stats.empty_stats()
        stats.add_document(a, field_dls={"title": 6}, blind_tokens={"a" * 64})

        b = stats.empty_stats()
        stats.add_document(b, field_dls={"title": 6}, blind_tokens={"a" * 64})
        stats.remove_document(b, field_dls={"title": 6}, blind_tokens={"a" * 64})
        stats.add_document(b, field_dls={"title": 6}, blind_tokens={"a" * 64})

        assert a == b


# ---------------------------------------------------------------------------
# InMemoryStatsStore
# ---------------------------------------------------------------------------


class TestInMemoryStatsStore:
    def test_get_missing_returns_none(self):
        store = stats.InMemoryStatsStore()
        assert store.get("owner-A") is None

    def test_round_trip(self):
        store = stats.InMemoryStatsStore()
        store.put("owner-A", b"blob")
        assert store.get("owner-A") == b"blob"

    def test_overwrite(self):
        store = stats.InMemoryStatsStore()
        store.put("owner-A", b"v1")
        store.put("owner-A", b"v2")
        assert store.get("owner-A") == b"v2"

    def test_delete(self):
        store = stats.InMemoryStatsStore()
        store.put("owner-A", b"x")
        store.delete("owner-A")
        assert store.get("owner-A") is None

    def test_delete_missing_is_noop(self):
        stats.InMemoryStatsStore().delete("owner-A")  # does not raise

    def test_owner_isolation(self):
        store = stats.InMemoryStatsStore()
        store.put("owner-A", b"A")
        store.put("owner-B", b"B")
        assert store.get("owner-A") == b"A"
        assert store.get("owner-B") == b"B"


# ---------------------------------------------------------------------------
# Indexer-shape integration
# ---------------------------------------------------------------------------


class TestIndexerShape:
    """End-to-end: derive key → empty stats → index 3 docs → fetch +
    decrypt → compute IDF inputs → BM25 ready."""

    def test_full_round_trip_through_store(self, owner_key):
        store = stats.InMemoryStatsStore()
        key = stats.derive_stats_key(owner_key)

        # First commit: persist empty stats.
        store.put("owner-A", stats.pack_stats(stats.empty_stats(), key))

        # Index 3 documents (read-modify-write each time).
        docs = [
            ({"title": 5, "content": 100}, {"a" * 64, "b" * 64}),
            ({"title": 7, "content": 200}, {"a" * 64, "c" * 64}),
            ({"title": 4, "content": 50}, {"b" * 64, "c" * 64}),
        ]
        for field_dls, tokens in docs:
            blob = store.get("owner-A")
            assert blob is not None
            current = stats.unpack_stats(blob, key)
            stats.add_document(
                current, field_dls=field_dls, blind_tokens=tokens
            )
            store.put("owner-A", stats.pack_stats(current, key))

        # Read back final state.
        final = stats.unpack_stats(store.get("owner-A"), key)
        assert final.doc_count == 3
        assert final.field_doc_count == {"title": 3, "content": 3}
        assert final.field_total_dl == {"title": 16, "content": 350}
        # avg_dl[title] = 16/3 ≈ 5.333
        assert abs(final.average_dl("title") - 16 / 3) < 1e-9
        # avg_dl[content] = 350/3 ≈ 116.667
        assert abs(final.average_dl("content") - 350 / 3) < 1e-9
        # Each token appears in exactly 2 of 3 documents.
        assert final.df_for("a" * 64) == 2
        assert final.df_for("b" * 64) == 2
        assert final.df_for("c" * 64) == 2

    def test_remove_one_document(self, owner_key):
        """Deletion path: index 3 docs, remove the middle one, verify
        counters reflect only the remaining 2."""
        store = stats.InMemoryStatsStore()
        key = stats.derive_stats_key(owner_key)
        s = stats.empty_stats()
        stats.add_document(s, field_dls={"title": 5}, blind_tokens={"a" * 64})
        stats.add_document(s, field_dls={"title": 7}, blind_tokens={"a" * 64})
        stats.add_document(s, field_dls={"title": 4}, blind_tokens={"b" * 64})
        store.put("owner-A", stats.pack_stats(s, key))

        # Remove the middle doc.
        loaded = stats.unpack_stats(store.get("owner-A"), key)
        stats.remove_document(
            loaded, field_dls={"title": 7}, blind_tokens={"a" * 64}
        )
        store.put("owner-A", stats.pack_stats(loaded, key))

        final = stats.unpack_stats(store.get("owner-A"), key)
        assert final.doc_count == 2
        assert final.field_doc_count == {"title": 2}
        assert final.field_total_dl == {"title": 9}
        assert final.df_for("a" * 64) == 1
        assert final.df_for("b" * 64) == 1
