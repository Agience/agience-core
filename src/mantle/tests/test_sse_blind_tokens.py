"""Tests for MANTLE-SSE blind token generation.

Covers:

- :func:`OracleService.derive_sse_key` — key shape, determinism,
  per-owner separation, independence from the cell-key tree.
- :mod:`mantle.search.mantle.sse.blind_tokens` —
  :func:`blind_token` / :func:`prefix_blind_tokens` / :func:`blind_tokens_for_terms`:
  determinism, field separation, owner separation, prefix coverage,
  validation.
"""

from __future__ import annotations


import pytest
from cryptography.fernet import Fernet

from search.mantle.oracle import FernetMasterKeyStore, OracleService
from search.mantle.sse import blind_tokens as bt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def oracle() -> OracleService:
    """Fresh OracleService backed by an in-memory Fernet store."""
    fernet = Fernet(Fernet.generate_key())
    return OracleService(FernetMasterKeyStore(fernet))


@pytest.fixture
def owner_key(oracle: OracleService) -> bytes:
    return oracle.derive_sse_key("owner-A")


# ---------------------------------------------------------------------------
# OracleService.derive_sse_key
# ---------------------------------------------------------------------------


class TestDeriveOwnerSseKey:
    def test_returns_32_bytes(self, oracle: OracleService) -> None:
        key = oracle.derive_sse_key("owner-A")
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_deterministic(self, oracle: OracleService) -> None:
        # Same owner → same key, every call.
        k1 = oracle.derive_sse_key("owner-A")
        k2 = oracle.derive_sse_key("owner-A")
        k3 = oracle.derive_sse_key("owner-A")
        assert k1 == k2 == k3

    def test_per_owner_isolation(self, oracle: OracleService) -> None:
        # Different owners → cryptographically independent keys.
        k_a = oracle.derive_sse_key("owner-A")
        k_b = oracle.derive_sse_key("owner-B")
        k_c = oracle.derive_sse_key("owner-C")
        assert len({k_a, k_b, k_c}) == 3

    def test_independent_from_cell_key_tree(self, oracle: OracleService) -> None:
        # SSE key and cell key share the master but use distinct HKDF info.
        # They must be different — same master, different derived material.
        sse = oracle.derive_sse_key("owner-A")
        cell = oracle.derive_cell_key("owner-A", "collection-1", "anchor-1")
        assert sse != cell

    def test_empty_principal_id_rejected(self, oracle: OracleService) -> None:
        with pytest.raises(ValueError, match="principal_id is required"):
            oracle.derive_sse_key("")

    def test_survives_eviction(self, oracle: OracleService) -> None:
        # Evicting the cache must not change the derived key. The cache is
        # only a performance optimization — the master key is persisted.
        before = oracle.derive_sse_key("owner-A")
        oracle.evict("owner-A")
        after = oracle.derive_sse_key("owner-A")
        assert before == after


# ---------------------------------------------------------------------------
# blind_token
# ---------------------------------------------------------------------------


class TestBlindToken:
    def test_returns_64_hex_chars(self, owner_key: bytes) -> None:
        token = bt.blind_token(owner_key, bt.FIELD_TITLE, "artifact")
        assert len(token) == 64
        # All hex digits.
        int(token, 16)  # raises ValueError if non-hex

    def test_deterministic(self, owner_key: bytes) -> None:
        a = bt.blind_token(owner_key, bt.FIELD_TITLE, "artifact")
        b = bt.blind_token(owner_key, bt.FIELD_TITLE, "artifact")
        assert a == b

    def test_field_separation(self, owner_key: bytes) -> None:
        # Same term, different fields → distinct tokens.
        title = bt.blind_token(owner_key, bt.FIELD_TITLE, "artifact")
        desc = bt.blind_token(owner_key, bt.FIELD_DESCRIPTION, "artifact")
        tags = bt.blind_token(owner_key, bt.FIELD_TAGS, "artifact")
        content = bt.blind_token(owner_key, bt.FIELD_CONTENT, "artifact")
        assert len({title, desc, tags, content}) == 4

    def test_term_separation(self, owner_key: bytes) -> None:
        a = bt.blind_token(owner_key, bt.FIELD_TITLE, "artifact")
        b = bt.blind_token(owner_key, bt.FIELD_TITLE, "agency")
        assert a != b

    def test_owner_separation(self, oracle: OracleService) -> None:
        # Same field+term under different owner keys → distinct tokens.
        # Without this the encryption boundary collapses.
        key_a = oracle.derive_sse_key("owner-A")
        key_b = oracle.derive_sse_key("owner-B")
        token_a = bt.blind_token(key_a, bt.FIELD_TITLE, "artifact")
        token_b = bt.blind_token(key_b, bt.FIELD_TITLE, "artifact")
        assert token_a != token_b

    def test_unknown_field_rejected(self, owner_key: bytes) -> None:
        with pytest.raises(ValueError, match="unknown field"):
            bt.blind_token(owner_key, "x", "artifact")

    def test_empty_term_rejected(self, owner_key: bytes) -> None:
        with pytest.raises(ValueError, match="term is required"):
            bt.blind_token(owner_key, bt.FIELD_TITLE, "")

    def test_short_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            bt.blind_token(b"\x00" * 16, bt.FIELD_TITLE, "artifact")

    def test_non_bytes_key_rejected(self, owner_key: bytes) -> None:
        with pytest.raises(TypeError):
            bt.blind_token("not-bytes", bt.FIELD_TITLE, "artifact")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# prefix_blind_tokens
# ---------------------------------------------------------------------------


class TestPrefixBlindTokens:
    def test_title_generates_three_prefixes(self, owner_key: bytes) -> None:
        tokens = bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "artifact")
        assert len(tokens) == 3  # px3, px4, px5
        for t in tokens:
            assert len(t) == 64

    def test_tags_generates_three_prefixes(self, owner_key: bytes) -> None:
        tokens = bt.prefix_blind_tokens(owner_key, bt.FIELD_TAGS, "artifact")
        assert len(tokens) == 3

    def test_description_returns_empty(self, owner_key: bytes) -> None:
        # Description is not a prefix-eligible field.
        assert bt.prefix_blind_tokens(owner_key, bt.FIELD_DESCRIPTION, "artifact") == []

    def test_content_returns_empty(self, owner_key: bytes) -> None:
        # Content text is not prefix-indexed (too many entries).
        assert bt.prefix_blind_tokens(owner_key, bt.FIELD_CONTENT, "artifact") == []

    def test_short_term_truncates_prefix_set(self, owner_key: bytes) -> None:
        # Term shorter than the smallest prefix → no tokens.
        assert bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "ab") == []
        # Length exactly 3 → only px3.
        assert len(bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "art")) == 1
        # Length 4 → px3 + px4.
        assert len(bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "arts")) == 2
        # Length 5+ → all three.
        assert len(bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "artic")) == 3
        assert len(bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "artifact")) == 3

    def test_prefix_tokens_distinct_from_exact_token(self, owner_key: bytes) -> None:
        # Prefix tokens use a "px{N}:" namespace and must never collide with
        # the exact-match token for the same term.
        exact = bt.blind_token(owner_key, bt.FIELD_TITLE, "artifact")
        prefixes = bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "artifact")
        assert exact not in prefixes

    def test_prefix_tokens_distinct_from_each_other(self, owner_key: bytes) -> None:
        tokens = bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "artifact")
        assert len(set(tokens)) == 3

    def test_deterministic(self, owner_key: bytes) -> None:
        first = bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "artifact")
        second = bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, "artifact")
        assert first == second

    def test_owner_separation(self, oracle: OracleService) -> None:
        key_a = oracle.derive_sse_key("owner-A")
        key_b = oracle.derive_sse_key("owner-B")
        tokens_a = bt.prefix_blind_tokens(key_a, bt.FIELD_TITLE, "artifact")
        tokens_b = bt.prefix_blind_tokens(key_b, bt.FIELD_TITLE, "artifact")
        assert set(tokens_a).isdisjoint(set(tokens_b))


# ---------------------------------------------------------------------------
# prefix_blind_token (single-prefix helper)
# ---------------------------------------------------------------------------


class TestPrefixBlindToken:
    def test_matches_prefix_blind_tokens_output(self, owner_key: bytes) -> None:
        """The single-prefix helper must agree with the multi-prefix
        function for the same (term, length) pair — otherwise the
        indexer (which uses prefix_blind_token) would generate tokens
        the query engine (which may use prefix_blind_tokens) couldn't
        find."""
        term = "artifact"
        multi = bt.prefix_blind_tokens(owner_key, bt.FIELD_TITLE, term)
        for i, n in enumerate(bt.PREFIX_LENGTHS):
            if len(term) < n:
                break
            single = bt.prefix_blind_token(
                owner_key, bt.FIELD_TITLE, term[:n], n,
            )
            assert multi[i] == single

    def test_rejects_non_prefix_field(self, owner_key: bytes) -> None:
        with pytest.raises(ValueError, match="not eligible"):
            bt.prefix_blind_token(
                owner_key, bt.FIELD_DESCRIPTION, "art", 3,
            )

    def test_rejects_invalid_length(self, owner_key: bytes) -> None:
        with pytest.raises(ValueError, match="prefix length"):
            bt.prefix_blind_token(owner_key, bt.FIELD_TITLE, "ar", 2)

    def test_rejects_mismatched_prefix_length(self, owner_key: bytes) -> None:
        with pytest.raises(ValueError, match="length must equal"):
            # n=3 but prefix is 4 chars
            bt.prefix_blind_token(owner_key, bt.FIELD_TITLE, "arti", 3)

    def test_rejects_empty_prefix(self, owner_key: bytes) -> None:
        with pytest.raises(ValueError):
            bt.prefix_blind_token(owner_key, bt.FIELD_TITLE, "", 3)

    def test_rejects_unknown_field(self, owner_key: bytes) -> None:
        with pytest.raises(ValueError, match="unknown field"):
            bt.prefix_blind_token(owner_key, "x", "art", 3)


# ---------------------------------------------------------------------------
# blind_tokens_for_terms
# ---------------------------------------------------------------------------


class TestBlindTokensForTerms:
    def test_empty_input(self, owner_key: bytes) -> None:
        assert bt.blind_tokens_for_terms(owner_key, bt.FIELD_TITLE, []) == []

    def test_preserves_order_and_duplicates(self, owner_key: bytes) -> None:
        # Term frequency depends on duplicates surviving — the indexer
        # counts blind-token occurrences directly.
        terms = ["run", "runner", "run", "runs"]
        out = bt.blind_tokens_for_terms(owner_key, bt.FIELD_TITLE, terms)
        assert len(out) == 4
        assert out[0] == out[2]  # both "run" → same token
        assert out[0] != out[1]  # "run" vs "runner"
        assert out[0] != out[3]  # "run" vs "runs"

    def test_skips_empty_terms(self, owner_key: bytes) -> None:
        out = bt.blind_tokens_for_terms(
            owner_key, bt.FIELD_TITLE, ["foo", "", "bar"]
        )
        assert len(out) == 2

    def test_matches_individual_blind_token(self, owner_key: bytes) -> None:
        # Batch must agree element-wise with the per-term function.
        terms = ["foo", "bar", "baz"]
        batch = bt.blind_tokens_for_terms(owner_key, bt.FIELD_DESCRIPTION, terms)
        per_term = [
            bt.blind_token(owner_key, bt.FIELD_DESCRIPTION, t) for t in terms
        ]
        assert batch == per_term

    def test_unknown_field_rejected(self, owner_key: bytes) -> None:
        with pytest.raises(ValueError, match="unknown field"):
            bt.blind_tokens_for_terms(owner_key, "z", ["foo"])


# ---------------------------------------------------------------------------
# Field constants — sanity
# ---------------------------------------------------------------------------


class TestFieldConstants:
    def test_distinct(self) -> None:
        assert len({bt.FIELD_TITLE, bt.FIELD_DESCRIPTION, bt.FIELD_TAGS, bt.FIELD_CONTENT}) == 4

    def test_single_char(self) -> None:
        for f in (bt.FIELD_TITLE, bt.FIELD_DESCRIPTION, bt.FIELD_TAGS, bt.FIELD_CONTENT):
            assert len(f) == 1

    def test_valid_fields_complete(self) -> None:
        assert bt.VALID_FIELDS == {
            bt.FIELD_TITLE,
            bt.FIELD_DESCRIPTION,
            bt.FIELD_TAGS,
            bt.FIELD_CONTENT,
        }

    def test_prefix_fields_subset(self) -> None:
        assert bt.PREFIX_FIELDS == {bt.FIELD_TITLE, bt.FIELD_TAGS}
        assert bt.PREFIX_FIELDS.issubset(bt.VALID_FIELDS)
