"""Blind-token generator for MANTLE-SSE.

Per `internal design notes` § Blind Tokens::

    blind_token = HMAC-SHA256(owner_sse_key, field_prefix + ":" + stemmed_term)

The HMAC produces a 256-bit token, encoded as 64 hex chars to serve as the
S3 key suffix (and the dictionary key inside encrypted manifests). Tokens
are deterministic per ``(owner, field, term)``: same input yields the same
token; the S3 backing store sees only opaque hex strings — never plaintext.

Field prefixes are single ASCII characters to keep token payloads compact:

- ``t`` — title
- ``d`` — description
- ``g`` — tags (the canonical "g" matches the design doc; mnemonic: ta**g**)
- ``c`` — content text

Prefix tokens (px3 / px4 / px5) are pre-computed for ``title`` and ``tags``
only. Content text generates too many prefix entries to be worth indexing,
and prefix search on description fields adds little user-visible value.
"""

from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Iterable, List

# ---------------------------------------------------------------------------
# Field prefixes
# ---------------------------------------------------------------------------

FIELD_TITLE = "t"
FIELD_DESCRIPTION = "d"
FIELD_TAGS = "g"
FIELD_CONTENT = "c"

VALID_FIELDS: frozenset[str] = frozenset(
    {FIELD_TITLE, FIELD_DESCRIPTION, FIELD_TAGS, FIELD_CONTENT}
)

# Fields eligible for px3/px4/px5 prefix tokens at index time.
PREFIX_FIELDS: frozenset[str] = frozenset({FIELD_TITLE, FIELD_TAGS})

# Prefix-token character widths. Order matters for prefix_blind_tokens output.
PREFIX_LENGTHS = (3, 4, 5)

# Owner SSE key length — must match :data:`oracle._SSE_KEY_BYTES`.
_SSE_KEY_BYTES = 32


# ---------------------------------------------------------------------------
# Internal HMAC helper
# ---------------------------------------------------------------------------

def _hmac_hex(key: bytes, message: bytes) -> str:
    return hmac.new(key, message, sha256).hexdigest()


def _validate_key(owner_sse_key: bytes) -> None:
    if not isinstance(owner_sse_key, (bytes, bytearray)):
        raise TypeError(
            f"owner_sse_key must be bytes, got {type(owner_sse_key).__name__}"
        )
    if len(owner_sse_key) != _SSE_KEY_BYTES:
        raise ValueError(
            f"owner_sse_key must be {_SSE_KEY_BYTES} bytes, got {len(owner_sse_key)}"
        )


def _validate_field(field: str) -> None:
    if field not in VALID_FIELDS:
        raise ValueError(
            f"unknown field: {field!r}; expected one of {sorted(VALID_FIELDS)}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def blind_token(owner_sse_key: bytes, field: str, term: str) -> str:
    """Generate the blind token for a single ``(field, term)`` pair.

    Returns 64 hex chars (256 bits). Deterministic for a given owner key.
    The same term in different fields (or under different owner keys)
    produces independent, unrelated tokens — by design.
    """
    _validate_key(owner_sse_key)
    _validate_field(field)
    if not term:
        raise ValueError("term is required")
    payload = f"{field}:{term}".encode("utf-8")
    return _hmac_hex(bytes(owner_sse_key), payload)


def prefix_blind_token(
    owner_sse_key: bytes, field: str, prefix: str, n: int,
) -> str:
    """Generate one prefix blind token for an explicit ``(prefix, n)`` pair.

    Computes ``HMAC-SHA256(owner_sse_key, "px{n}:{field}:{prefix}")``.
    Use when the indexer (or query engine) already has the prefix string
    in hand — saves recomputing the HMAC for every term that shares it.
    Pre-computing per (n, prefix) lets the indexer aggregate term
    frequencies across all terms sharing a prefix into a single posting
    list entry.

    Constraints (mirror :func:`prefix_blind_tokens`):

    - ``field`` must be in :data:`PREFIX_FIELDS` (title or tags).
    - ``n`` must be in :data:`PREFIX_LENGTHS` (3, 4, or 5).
    - ``prefix`` length must equal ``n``.
    """
    _validate_key(owner_sse_key)
    _validate_field(field)
    if field not in PREFIX_FIELDS:
        raise ValueError(
            f"field {field!r} is not eligible for prefix tokens; "
            f"expected one of {sorted(PREFIX_FIELDS)}"
        )
    if n not in PREFIX_LENGTHS:
        raise ValueError(
            f"prefix length {n} not in {PREFIX_LENGTHS}"
        )
    if not prefix or len(prefix) != n:
        raise ValueError(
            f"prefix length must equal n={n}; got prefix={prefix!r}"
        )
    payload = f"px{n}:{field}:{prefix}".encode("utf-8")
    return _hmac_hex(bytes(owner_sse_key), payload)


def prefix_blind_tokens(
    owner_sse_key: bytes, field: str, term: str
) -> List[str]:
    """Generate prefix blind tokens for a term in a prefix-eligible field.

    Produces one token per prefix length in :data:`PREFIX_LENGTHS` where the
    term is at least that long. Returns an empty list for fields outside
    :data:`PREFIX_FIELDS` (description, content) or for terms shorter
    than the smallest prefix length.

    The token payload format is ``"px{N}:{field}:{prefix}"`` so prefix
    tokens never collide with exact tokens (which use ``"{field}:{term}"``).
    """
    _validate_key(owner_sse_key)
    _validate_field(field)
    if field not in PREFIX_FIELDS:
        return []
    if not term:
        return []
    out: List[str] = []
    key_bytes = bytes(owner_sse_key)
    for n in PREFIX_LENGTHS:
        if len(term) < n:
            break
        payload = f"px{n}:{field}:{term[:n]}".encode("utf-8")
        out.append(_hmac_hex(key_bytes, payload))
    return out


def blind_tokens_for_terms(
    owner_sse_key: bytes,
    field: str,
    terms: Iterable[str],
) -> List[str]:
    """Generate blind tokens for an iterable of terms in a single field.

    Order is preserved. Duplicates are kept — the indexer needs the raw
    sequence to compute term frequencies; the query path deduplicates
    downstream when uniqueness is desired.
    """
    _validate_key(owner_sse_key)
    _validate_field(field)
    key_bytes = bytes(owner_sse_key)
    out: List[str] = []
    for term in terms:
        if not term:
            continue
        payload = f"{field}:{term}".encode("utf-8")
        out.append(_hmac_hex(key_bytes, payload))
    return out


__all__ = [
    "FIELD_TITLE",
    "FIELD_DESCRIPTION",
    "FIELD_TAGS",
    "FIELD_CONTENT",
    "VALID_FIELDS",
    "PREFIX_FIELDS",
    "PREFIX_LENGTHS",
    "blind_token",
    "blind_tokens_for_terms",
    "prefix_blind_token",
    "prefix_blind_tokens",
]
