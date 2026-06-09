"""English analysis pipeline for MANTLE-SSE.

Mirrors the structure of OpenSearch's `english_analyzer`:

    standard tokenizer → lowercase → possessive stemmer → stop words → Porter stemmer

Pure Python, no NLTK dependency. The Porter (1980) stemmer is implemented
inline; it is deterministic, well-defined, and produces stable stems
suitable for blind-token derivation in :mod:`mantle.search.mantle.sse.blind_tokens`.

Index-time and query-time both call :func:`tokenize`, which guarantees the
same string maps to the same blind tokens on both paths. The stemmer is
fixed; if it ever changes (e.g., to Snowball/Porter2), every existing index
must be rebuilt — there is no in-place migration. That is why this module
has no dialect or version flag: stemmer choice is part of the index format.

Public API:

- :func:`tokenize` — full pipeline; returns the list of stems in input order.
- :data:`STOP_WORDS` — the set used by :func:`is_stop_word`. Matches Lucene's
  default English stop list (`_english_`) so behavior parallels the
  OpenSearch path during the migration window.

The stages are also exposed individually for testing:

- :func:`split_words`
- :func:`strip_possessive`
- :func:`is_stop_word`
- :func:`porter_stem`
"""

from __future__ import annotations

import re
from typing import List


# ---------------------------------------------------------------------------
# Stop word list — Lucene's `_english_` default
# ---------------------------------------------------------------------------

STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by",
    "for", "if", "in", "into", "is", "it",
    "no", "not", "of", "on", "or", "such",
    "that", "the", "their", "then", "there", "these",
    "they", "this", "to", "was", "will", "with",
})


# ---------------------------------------------------------------------------
# Stage 1 — tokenize raw text
# ---------------------------------------------------------------------------

# Match word-character runs, allowing internal/trailing apostrophes so
# possessives like ``alice's`` and ``workers'`` survive as single tokens for
# :func:`strip_possessive` to handle. Mirrors Lucene's StandardTokenizer for
# ASCII English; corner cases (URL splitting, CJK segmentation) are out of
# scope for the SSE MVP. ``\w`` is Unicode-aware, so accented characters and
# digits both work.
_WORD_RE = re.compile(r"\w+(?:'\w*)*", flags=re.UNICODE)


def split_words(text: str) -> List[str]:
    """Split text into raw word tokens. Empty tokens are dropped."""
    if not text:
        return []
    return _WORD_RE.findall(text)


# ---------------------------------------------------------------------------
# Stage 2 — lowercase (handled by str.lower at the caller)
# ---------------------------------------------------------------------------

# Inlined as ``token.lower()`` in :func:`tokenize`. No separate function:
# str.lower is the canonical implementation, no need to wrap it.


# ---------------------------------------------------------------------------
# Stage 3 — possessive stemmer (English)
# ---------------------------------------------------------------------------

def strip_possessive(token: str) -> str:
    """Strip a trailing English possessive (``'s`` or ``s'``) from a token.

    Matches Lucene's ``english_possessive_stemmer``:

    >>> strip_possessive("alice's")
    'alice'
    >>> strip_possessive("workers'")
    'workers'
    >>> strip_possessive("apple")
    'apple'
    """
    if len(token) >= 2 and token.endswith("'s"):
        return token[:-2]
    if len(token) >= 2 and token.endswith("s'"):
        return token[:-1]
    return token


# ---------------------------------------------------------------------------
# Stage 4 — stop word filter
# ---------------------------------------------------------------------------

def is_stop_word(token: str) -> bool:
    """True if ``token`` is in the English stop word list."""
    return token in STOP_WORDS


# ---------------------------------------------------------------------------
# Stage 5 — Porter (1980) stemmer
# ---------------------------------------------------------------------------
#
# Reference: M.F. Porter, "An algorithm for suffix stripping" (1980),
# Program 14(3): 130-137. Public-domain algorithm.
#
# Notation used in the comments below mirrors Porter's paper:
#   m       = "measure" — number of (VC) patterns in the stem
#   *v*     = stem contains a vowel
#   *S      = stem ends with S
#   *d      = stem ends with a double consonant
#   *o      = stem ends c-v-c where the final c is not w, x, or y
#
# `y` is treated as a consonant when preceded by a vowel and as a vowel
# otherwise — Porter's rule, carried verbatim.

_VOWELS = frozenset("aeiou")


def _is_vowel(stem: str, i: int) -> bool:
    """Porter's vowel/consonant classification at position ``i``."""
    c = stem[i]
    if c in _VOWELS:
        return True
    if c == "y":
        # `y` is a vowel only when preceded by a consonant (or at position 0
        # acts as a consonant per Porter — the paper says "y is consonantal
        # at the start of a word"). Implementation follows the paper.
        return i > 0 and not _is_vowel(stem, i - 1)
    return False


def _measure(stem: str) -> int:
    """Compute Porter's measure m — number of VC patterns."""
    if not stem:
        return 0
    # Build the C/V pattern, collapsing runs.
    pattern: List[str] = []
    for i in range(len(stem)):
        kind = "V" if _is_vowel(stem, i) else "C"
        if not pattern or pattern[-1] != kind:
            pattern.append(kind)
    # Count VC pairs: positions where 'V' is immediately followed by 'C'.
    return sum(1 for i in range(len(pattern) - 1) if pattern[i] == "V" and pattern[i + 1] == "C")


def _contains_vowel(stem: str) -> bool:
    return any(_is_vowel(stem, i) for i in range(len(stem)))


def _ends_double_consonant(stem: str) -> bool:
    """*d — stem ends with a double consonant (same letter, both consonants)."""
    if len(stem) < 2:
        return False
    if stem[-1] != stem[-2]:
        return False
    return not _is_vowel(stem, len(stem) - 1)


def _ends_cvc(stem: str) -> bool:
    """*o — stem ends c-v-c where the final c is not w, x, or y."""
    if len(stem) < 3:
        return False
    if _is_vowel(stem, len(stem) - 3):
        return False
    if not _is_vowel(stem, len(stem) - 2):
        return False
    if _is_vowel(stem, len(stem) - 1):
        return False
    return stem[-1] not in "wxy"


def _replace_suffix(stem: str, suffix: str, replacement: str) -> str:
    return stem[: -len(suffix)] + replacement


# --- Step 1a -----------------------------------------------------------------
# Plurals and -s endings.

def _step_1a(stem: str) -> str:
    if stem.endswith("sses"):
        return _replace_suffix(stem, "sses", "ss")
    if stem.endswith("ies"):
        return _replace_suffix(stem, "ies", "i")
    if stem.endswith("ss"):
        return stem
    if stem.endswith("s"):
        return stem[:-1]
    return stem


# --- Step 1b -----------------------------------------------------------------
# Past tense / -ing.

def _step_1b(stem: str) -> str:
    if stem.endswith("eed"):
        if _measure(stem[:-3]) > 0:
            return stem[:-1]  # eed → ee
        return stem
    fired = False
    new_stem = stem
    if stem.endswith("ed"):
        candidate = stem[:-2]
        if _contains_vowel(candidate):
            new_stem = candidate
            fired = True
    elif stem.endswith("ing"):
        candidate = stem[:-3]
        if _contains_vowel(candidate):
            new_stem = candidate
            fired = True
    if not fired:
        return stem
    # Step 1b' — restore canonical form after stripping.
    if new_stem.endswith(("at", "bl", "iz")):
        return new_stem + "e"
    if (
        _ends_double_consonant(new_stem)
        and new_stem[-1] not in "lsz"
    ):
        return new_stem[:-1]
    if _measure(new_stem) == 1 and _ends_cvc(new_stem):
        return new_stem + "e"
    return new_stem


# --- Step 1c -----------------------------------------------------------------
# y → i if the stem contains a vowel.

def _step_1c(stem: str) -> str:
    if stem.endswith("y") and _contains_vowel(stem[:-1]):
        return stem[:-1] + "i"
    return stem


# --- Step 2 ------------------------------------------------------------------

_STEP2_RULES = (
    ("ational", "ate"),
    ("tional", "tion"),
    ("enci", "ence"),
    ("anci", "ance"),
    ("izer", "ize"),
    ("bli", "ble"),
    ("alli", "al"),
    ("entli", "ent"),
    ("eli", "e"),
    ("ousli", "ous"),
    ("ization", "ize"),
    ("ation", "ate"),
    ("ator", "ate"),
    ("alism", "al"),
    ("iveness", "ive"),
    ("fulness", "ful"),
    ("ousness", "ous"),
    ("aliti", "al"),
    ("iviti", "ive"),
    ("biliti", "ble"),
    ("logi", "log"),
)


def _step_2(stem: str) -> str:
    for suffix, replacement in _STEP2_RULES:
        if stem.endswith(suffix):
            candidate = stem[: -len(suffix)]
            if _measure(candidate) > 0:
                return candidate + replacement
            return stem
    return stem


# --- Step 3 ------------------------------------------------------------------

_STEP3_RULES = (
    ("icate", "ic"),
    ("ative", ""),
    ("alize", "al"),
    ("iciti", "ic"),
    ("ical", "ic"),
    ("ful", ""),
    ("ness", ""),
)


def _step_3(stem: str) -> str:
    for suffix, replacement in _STEP3_RULES:
        if stem.endswith(suffix):
            candidate = stem[: -len(suffix)]
            if _measure(candidate) > 0:
                return candidate + replacement
            return stem
    return stem


# --- Step 4 ------------------------------------------------------------------

_STEP4_RULES = (
    "al", "ance", "ence", "er", "ic", "able", "ible", "ant",
    "ement", "ment", "ent", "ou", "ism", "ate", "iti", "ous",
    "ive", "ize",
)


def _step_4(stem: str) -> str:
    # `ion` is a special case: only strip when preceded by `s` or `t`.
    if stem.endswith("ion"):
        candidate = stem[:-3]
        if (
            _measure(candidate) > 1
            and candidate
            and candidate[-1] in ("s", "t")
        ):
            return candidate
        return stem
    # Order longest-first to avoid `er` shadowing `ement`.
    for suffix in sorted(_STEP4_RULES, key=len, reverse=True):
        if stem.endswith(suffix):
            candidate = stem[: -len(suffix)]
            if _measure(candidate) > 1:
                return candidate
            return stem
    return stem


# --- Step 5 ------------------------------------------------------------------

def _step_5a(stem: str) -> str:
    if stem.endswith("e"):
        candidate = stem[:-1]
        m = _measure(candidate)
        if m > 1:
            return candidate
        if m == 1 and not _ends_cvc(candidate):
            return candidate
    return stem


def _step_5b(stem: str) -> str:
    if (
        _measure(stem) > 1
        and _ends_double_consonant(stem)
        and stem.endswith("l")
    ):
        return stem[:-1]
    return stem


def porter_stem(token: str) -> str:
    """Apply the full Porter (1980) algorithm. Token must be lowercase ASCII.

    Tokens shorter than 3 characters are returned unchanged — Porter's
    convention. Non-ASCII tokens pass through untouched; SSE indexes them
    by their lowercase form.
    """
    if len(token) <= 2:
        return token
    if not token.isascii() or not token.isalpha():
        return token
    s = _step_1a(token)
    s = _step_1b(s)
    s = _step_1c(s)
    s = _step_2(s)
    s = _step_3(s)
    s = _step_4(s)
    s = _step_5a(s)
    s = _step_5b(s)
    return s


# ---------------------------------------------------------------------------
# Public pipeline
# ---------------------------------------------------------------------------

def tokenize(text: str) -> List[str]:
    """Full English analysis pipeline.

    Stages (in order):

    1. Split on non-word characters.
    2. Lowercase.
    3. Strip English possessive (``'s`` / ``s'``).
    4. Drop empty tokens.
    5. Drop stop words.
    6. Porter stem.
    7. Drop tokens that became empty after stemming.

    Returns the stems in input order. Duplicate stems are *not* deduplicated
    here — callers that need term frequencies (the SSE indexer) compute
    them from the returned list; callers that need the unique term set (the
    query path) deduplicate downstream.
    """
    if not text:
        return []
    out: List[str] = []
    for raw in split_words(text):
        token = strip_possessive(raw.lower())
        if not token:
            continue
        if is_stop_word(token):
            continue
        stem = porter_stem(token)
        if not stem:
            continue
        out.append(stem)
    return out


def bigrams(stems: List[str]) -> List[str]:
    """Return adjacent-pair bigram tokens for phrase indexing.

    Example: ["platform", "artifact"] → ["platform artifact"]

    Used by the SSE indexer to write phrase posting lists at commit time
    and by the SSE query engine to look up phrases when the user's query
    is quoted. The space separator is safe because individual stems
    contain only alphabetic characters after the Porter pipeline — no
    stem can contain a space.

    Duplicate bigrams are *not* deduplicated here — callers handle
    uniqueness the same way they do for unigrams.
    """
    if len(stems) < 2:
        return []
    return [f"{stems[i]} {stems[i + 1]}" for i in range(len(stems) - 1)]


__all__ = [
    "STOP_WORDS",
    "bigrams",
    "is_stop_word",
    "porter_stem",
    "split_words",
    "strip_possessive",
    "tokenize",
]
