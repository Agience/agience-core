"""Tests for :mod:`mantle.search.mantle.sse.tokenizer`.

Coverage:

- :func:`split_words` — word boundaries, apostrophes, Unicode, empty input.
- :func:`strip_possessive` — ``'s`` and ``s'`` removal; non-possessives.
- :func:`is_stop_word` / :data:`STOP_WORDS` — list shape + membership.
- :func:`porter_stem` — every canonical example from Porter (1980), grouped
  by step. The full set is ~80 cases; if the stemmer regresses on any one,
  every existing SSE index would have to be rebuilt — so the test suite
  is the contract.
- :func:`tokenize` — end-to-end pipeline including stop-word drop and
  possessive handling.
"""

from __future__ import annotations

import pytest

from search.mantle.sse.tokenizer import (
    STOP_WORDS,
    is_stop_word,
    porter_stem,
    split_words,
    strip_possessive,
    tokenize,
)


# ---------------------------------------------------------------------------
# split_words
# ---------------------------------------------------------------------------


class TestSplitWords:
    def test_simple_sentence(self) -> None:
        assert split_words("hello world") == ["hello", "world"]

    def test_punctuation_dropped(self) -> None:
        assert split_words("hello, world!") == ["hello", "world"]

    def test_multiple_whitespace(self) -> None:
        assert split_words("a  \t b\n c") == ["a", "b", "c"]

    def test_apostrophe_preserved_internally(self) -> None:
        assert split_words("alice's apple") == ["alice's", "apple"]

    def test_trailing_apostrophe_preserved(self) -> None:
        assert split_words("workers' rights") == ["workers'", "rights"]

    def test_compound_apostrophe(self) -> None:
        # Stemmer can't normalize this, but it should survive tokenization
        # as one unit rather than splitting into pieces.
        assert split_words("rock'n'roll") == ["rock'n'roll"]

    def test_hyphen_splits(self) -> None:
        assert split_words("hello-world") == ["hello", "world"]

    def test_underscore_kept(self) -> None:
        # `_` is a word character — kept as part of identifiers.
        assert split_words("foo_bar baz") == ["foo_bar", "baz"]

    def test_unicode_letters(self) -> None:
        assert split_words("café résumé") == ["café", "résumé"]

    def test_empty(self) -> None:
        assert split_words("") == []

    def test_whitespace_only(self) -> None:
        assert split_words("   \t\n  ") == []

    def test_punctuation_only(self) -> None:
        assert split_words("...!!!??") == []

    def test_digits_kept(self) -> None:
        assert split_words("foo 42 bar") == ["foo", "42", "bar"]


# ---------------------------------------------------------------------------
# strip_possessive
# ---------------------------------------------------------------------------


class TestStripPossessive:
    def test_apostrophe_s(self) -> None:
        assert strip_possessive("alice's") == "alice"

    def test_s_apostrophe(self) -> None:
        # Plural possessive — drop the apostrophe only, keep the s.
        assert strip_possessive("workers'") == "workers"

    def test_no_possessive(self) -> None:
        assert strip_possessive("apple") == "apple"

    def test_internal_apostrophe(self) -> None:
        # Doesn't end in `'s` or `s'` — leave alone.
        assert strip_possessive("can't") == "can't"

    def test_short_token(self) -> None:
        # Length-1 tokens never trigger the strip.
        assert strip_possessive("a") == "a"

    def test_empty(self) -> None:
        assert strip_possessive("") == ""


# ---------------------------------------------------------------------------
# stop words
# ---------------------------------------------------------------------------


class TestStopWords:
    def test_known_stop_words(self) -> None:
        for word in ("the", "and", "is", "of", "to"):
            assert is_stop_word(word), word

    def test_non_stop_words(self) -> None:
        for word in ("artifact", "claude", "agience", "search"):
            assert not is_stop_word(word), word

    def test_case_sensitive(self) -> None:
        # Pipeline lowercases before this check; stop word membership is
        # lowercase-only by design.
        assert not is_stop_word("The")
        assert is_stop_word("the")

    def test_stop_words_is_frozen(self) -> None:
        assert isinstance(STOP_WORDS, frozenset)


# ---------------------------------------------------------------------------
# Porter stemmer — canonical cases from Porter (1980)
# ---------------------------------------------------------------------------


# Cases drawn from Porter's original paper. Grouped by the algorithm step
# that handles them so failures localize.
_STEP_1A_CASES = [
    ("caresses", "caress"),
    ("ponies", "poni"),
    ("ties", "ti"),
    ("caress", "caress"),
    ("cats", "cat"),
]

# Note: Porter's paper shows the step-1b *intermediate* output for some words
# (agreed→agree, conflated→conflate, troubled→trouble), but the final stems
# after steps 2-5 strip the trailing `e` further (m=1, not *o). The values
# below match Porter's reference implementation's full-pipeline output.
_STEP_1B_CASES = [
    ("feed", "feed"),
    ("agreed", "agre"),
    ("plastered", "plaster"),
    ("bled", "bled"),
    ("motoring", "motor"),
    ("sing", "sing"),
    ("conflated", "conflat"),
    ("troubled", "troubl"),
    ("sized", "size"),
    ("hopping", "hop"),
    ("tanned", "tan"),
    ("falling", "fall"),
    ("hissing", "hiss"),
    ("fizzed", "fizz"),
    ("failing", "fail"),
    ("filing", "file"),
]

_STEP_1C_CASES = [
    ("happy", "happi"),
    ("sky", "sky"),
]

_STEP_2_CASES = [
    ("relational", "relat"),
    ("conditional", "condit"),
    ("rational", "ration"),
    ("valenci", "valenc"),
    ("hesitanci", "hesit"),
    ("digitizer", "digit"),
    ("conformabli", "conform"),
    ("radicalli", "radic"),
    ("differentli", "differ"),
    ("vileli", "vile"),
    ("analogousli", "analog"),
    ("vietnamization", "vietnam"),
    ("predication", "predic"),
    ("operator", "oper"),
    ("feudalism", "feudal"),
    ("decisiveness", "decis"),
    ("hopefulness", "hope"),
    ("callousness", "callous"),
    ("formaliti", "formal"),
    ("sensitiviti", "sensit"),
    ("sensibiliti", "sensibl"),
]

_STEP_3_CASES = [
    ("triplicate", "triplic"),
    ("formative", "form"),
    ("formalize", "formal"),
    ("electriciti", "electr"),
    ("electrical", "electr"),
    ("hopeful", "hope"),
    ("goodness", "good"),
]

_STEP_4_CASES = [
    ("revival", "reviv"),
    ("allowance", "allow"),
    ("inference", "infer"),
    ("airliner", "airlin"),
    ("gyroscopic", "gyroscop"),
    ("adjustable", "adjust"),
    ("defensible", "defens"),
    ("irritant", "irrit"),
    ("replacement", "replac"),
    ("adjustment", "adjust"),
    ("dependent", "depend"),
    ("adoption", "adopt"),
    ("homologou", "homolog"),
    ("communism", "commun"),
    ("activate", "activ"),
    ("angulariti", "angular"),
    ("homologous", "homolog"),
    ("effective", "effect"),
    ("bowdlerize", "bowdler"),
]

_STEP_5_CASES = [
    ("probate", "probat"),
    ("rate", "rate"),
    ("cease", "ceas"),
    ("controll", "control"),
    ("roll", "roll"),
]


class TestPorterStem:
    @pytest.mark.parametrize("word,expected", _STEP_1A_CASES)
    def test_step_1a(self, word: str, expected: str) -> None:
        assert porter_stem(word) == expected

    @pytest.mark.parametrize("word,expected", _STEP_1B_CASES)
    def test_step_1b(self, word: str, expected: str) -> None:
        assert porter_stem(word) == expected

    @pytest.mark.parametrize("word,expected", _STEP_1C_CASES)
    def test_step_1c(self, word: str, expected: str) -> None:
        assert porter_stem(word) == expected

    @pytest.mark.parametrize("word,expected", _STEP_2_CASES)
    def test_step_2(self, word: str, expected: str) -> None:
        assert porter_stem(word) == expected

    @pytest.mark.parametrize("word,expected", _STEP_3_CASES)
    def test_step_3(self, word: str, expected: str) -> None:
        assert porter_stem(word) == expected

    @pytest.mark.parametrize("word,expected", _STEP_4_CASES)
    def test_step_4(self, word: str, expected: str) -> None:
        assert porter_stem(word) == expected

    @pytest.mark.parametrize("word,expected", _STEP_5_CASES)
    def test_step_5(self, word: str, expected: str) -> None:
        assert porter_stem(word) == expected

    def test_short_token_unchanged(self) -> None:
        # Porter's convention: tokens of length <= 2 pass through.
        for token in ("a", "i", "is", "of", "to"):
            assert porter_stem(token) == token

    def test_empty_string(self) -> None:
        assert porter_stem("") == ""

    def test_non_alpha_unchanged(self) -> None:
        # Apostrophes, digits, hyphens — pass through untouched.
        assert porter_stem("rock'n'roll") == "rock'n'roll"
        assert porter_stem("abc123") == "abc123"

    def test_non_ascii_unchanged(self) -> None:
        # Non-ASCII tokens are indexed by their lowercase form, not stemmed.
        assert porter_stem("café") == "café"

    def test_deterministic(self) -> None:
        # Same input → same output, every time. Required for blind-token
        # stability across index rebuilds.
        for word in ("artifact", "running", "controller", "happy"):
            assert porter_stem(word) == porter_stem(word) == porter_stem(word)


# ---------------------------------------------------------------------------
# tokenize — end-to-end pipeline
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_simple(self) -> None:
        # "the" is a stop word; "quick", "brown", "fox" stem to themselves
        # (none of the suffix rules apply).
        assert tokenize("The quick brown fox") == ["quick", "brown", "fox"]

    def test_drops_stop_words(self) -> None:
        # Every input token is a stop word.
        assert tokenize("the and of with") == []

    def test_strips_possessives(self) -> None:
        assert tokenize("Alice's apple") == ["alic", "appl"]

    def test_lowercases(self) -> None:
        assert tokenize("CONTROLLERS") == tokenize("controllers")

    def test_punctuation(self) -> None:
        assert tokenize("Hello, world!") == ["hello", "world"]

    def test_preserves_order(self) -> None:
        # Order is preserved; duplicate stems are kept (TF needs them).
        assert tokenize("running runner runs") == ["run", "runner", "run"]

    def test_empty(self) -> None:
        assert tokenize("") == []

    def test_only_stop_words_and_punctuation(self) -> None:
        assert tokenize("the!  and... of?") == []

    def test_real_phrase(self) -> None:
        # End-to-end on a representative phrase.
        result = tokenize("The agencies are managing artifacts collaboratively.")
        # Expected stems (Porter 1980):
        #   agencies → agenc
        #   managing → manag
        #   artifacts → artifact
        #   collaboratively → collabor
        # "the" and "are" are stop words; dropped.
        assert result == ["agenc", "manag", "artifact", "collabor"]

    def test_index_query_consistency(self) -> None:
        # The fundamental contract: same string at index time and query time
        # yields the same token list. Without this, blind tokens never match.
        text = "Searching artifacts for grants"
        assert tokenize(text) == tokenize(text)


# ---------------------------------------------------------------------------
# bigrams — phrase token generation
# ---------------------------------------------------------------------------


class TestBigrams:
    def test_two_stems(self) -> None:
        from search.mantle.sse.tokenizer import bigrams
        assert bigrams(["platform", "artifact"]) == ["platform artifact"]

    def test_three_stems(self) -> None:
        from search.mantle.sse.tokenizer import bigrams
        result = bigrams(["a", "b", "c"])
        assert result == ["a b", "b c"]

    def test_single_stem_returns_empty(self) -> None:
        from search.mantle.sse.tokenizer import bigrams
        assert bigrams(["only"]) == []

    def test_empty_list_returns_empty(self) -> None:
        from search.mantle.sse.tokenizer import bigrams
        assert bigrams([]) == []

    def test_space_separator_safe(self) -> None:
        # Individual stems never contain spaces (Porter output is alpha-only),
        # so bigrams can't collide with unigrams.
        from search.mantle.sse.tokenizer import bigrams
        pairs = bigrams(["foo", "bar"])
        assert all(" " in p for p in pairs)

    def test_preserves_order(self) -> None:
        from search.mantle.sse.tokenizer import bigrams
        stems = ["one", "two", "three", "four"]
        result = bigrams(stems)
        assert result == ["one two", "two three", "three four"]

    def test_composed_with_tokenize(self) -> None:
        from search.mantle.sse.tokenizer import bigrams, tokenize
        # "platform artifacts" → stems ["platform", "artifact"]
        # bigrams → ["platform artifact"]
        stems = tokenize("platform artifacts")
        assert bigrams(stems) == ["platform artifact"]

