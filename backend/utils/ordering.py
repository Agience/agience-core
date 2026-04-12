# utils/ordering.py
# Fractional indexing for lexicographic artifact ordering (base-62).
# Pure functions — no DB dependency.

_ALPH = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def after_key(a: str | None) -> str:
    """Return a key that sorts strictly after *a* (or 'U' if *a* is None)."""
    if not a:
        return "U"
    last = _ALPH.find(a[-1])
    if last == -1 or last == len(_ALPH) - 1:
        return a + "U"
    return a[:-1] + _ALPH[last + 1]


def mid_key(a: str | None, b: str | None) -> str:
    """Return a key that sorts between *a* and *b* (minimalist fractional indexing)."""
    pad = "U"
    if a is None and b is None:
        return pad
    if a is None:
        a = ""
    if b is None:
        return a + pad
    i = 0
    while True:
        ca = _ALPH.find(a[i]) if i < len(a) else _ALPH.find(pad)
        cb = _ALPH.find(b[i]) if i < len(b) else len(_ALPH) - 1
        if ca + 1 < cb:
            return (a[:i] if i < len(a) else a) + _ALPH[(ca + cb) // 2]
        i += 1
        if i > max(len(a), len(b)) + 4:
            return a + _ALPH[1]
