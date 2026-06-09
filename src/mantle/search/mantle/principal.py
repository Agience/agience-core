"""Cell-key principal resolution — the master-key root for MANTLE cells.

A MANTLE cell's master key roots at the collection's **origin root** (the
immutable top of its creation chain), NOT at provenance (``created_by``) or the
mutable grant set. Index and query both resolve the principal the same way, so
they derive the same key for the same collection. There is no "owner" — access
is by grant, not ownership.

See :func:`db.arango.get_origin_root` and
``.dev/features/anchors-and-anchorsets.md`` §5.
"""

from __future__ import annotations

from db import arango as db_arango


def resolve_cell_principal(db, collection_id: str) -> str:
    """The encrypted-search principal for ``collection_id`` — its origin root.

    Stable and single-valued for the collection's whole sub-tree, so a cell
    encrypted at index time is decryptable at query time under the same key.
    Returns ``collection_id`` itself when the chain can't be walked, and ``""``
    for an empty input (callers skip empty principals).
    """
    if not collection_id:
        return ""
    try:
        root = db_arango.get_origin_root(db, collection_id)
        return root or collection_id
    except Exception:
        return collection_id
