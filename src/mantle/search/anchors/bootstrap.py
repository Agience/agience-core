"""Light-training bootstrap — seed the shared coordinate system from the
platform's common grounded knowledge.

The AnchorSet is mandatory (canonical plan §3): there is ONE path and it is
anchor-routed, so the set has to exist before the first vector is indexed or
queried. We bootstrap it by clustering the platform seed corpus — the common
grounded knowledge every deployment ships with — and admitting representative
items as the initial anchors. The set grows from there as the manifold grows
(``grow.propose_anchor``).

Used by both :func:`store.require_live_anchorset` (auto-bootstrap on first use)
and ``manage_anchors.py bootstrap`` (explicit pre-warm at deploy).

INVARIANT (§1): public, non-authorizing geometry. No keys, no light-cone, no
ledger — just embeddings of public seed text.
"""

from __future__ import annotations

import logging

from .anchorset import AnchorSet

logger = logging.getLogger(__name__)

# Default number of anchors to admit when bootstrapping from the seed corpus.
DEFAULT_K = 24


def gather_seed_corpus() -> list[tuple[str, str]]:
    """Return ``(label, text)`` for each platform seed artifact — the common
    grounded knowledge that seeds the universal coordinate system."""
    import yaml

    from kernel import config

    root = config.BASE_DIR / "package" / "seeds" / "platform" / "artifacts"
    corpus: list[tuple[str, str]] = []
    if not root.is_dir():
        return corpus
    for path in sorted(root.glob("*.yaml")):
        try:
            body = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(body, dict):
            continue
        label = str(body.get("slug") or body.get("name") or path.stem)
        parts = [
            str(body.get("name", "")),
            str(body.get("description", "")),
            str(body.get("content", "")),
        ]
        text = " ".join(p for p in parts if p and p != "None").strip()
        if text:
            corpus.append((label, text))
    return corpus


def bootstrap_anchorset(repo=None, *, k: int = DEFAULT_K) -> AnchorSet:
    """Embed the platform seed corpus, cluster into ``k`` anchors, persist them
    as artifacts through ``repo`` (when given), and return the live
    :class:`AnchorSet`.

    Each admitted medoid becomes a ``vnd.agience.anchor+json`` artifact in the
    ``agience-anchorset`` collection (the AnchorSet IS that collection).

    Raises :class:`RuntimeError` when the seed corpus is absent or the
    embeddings provider returns nothing — there is no flat/raw-vector fallback,
    so callers must surface the error (the geometry layer cannot route without
    anchors).
    """
    corpus = gather_seed_corpus()
    if not corpus:
        raise RuntimeError(
            "Cannot bootstrap AnchorSet: no seed corpus under "
            "package/seeds/platform/artifacts."
        )

    from kernel.embeddings import Embeddings, model_id as emb_model_id

    vectors = Embeddings()([t for _, t in corpus])
    items = [(corpus[i][0], vectors[i]) for i in range(len(vectors)) if vectors[i]]
    if not items:
        raise RuntimeError(
            "Cannot bootstrap AnchorSet: embeddings provider returned nothing "
            "(set EMBEDDINGS_URI and ensure the embeddings server is running)."
        )

    dim = len(items[0][1])
    aset = AnchorSet(model_id=emb_model_id(), dim=dim).bootstrap(items, k=k)
    if repo is not None:
        repo.bulk_add(aset.anchors)
    logger.info(
        "Bootstrapped AnchorSet: %d anchors from %d seed items (dim=%d, model=%s)",
        len(aset), len(items), dim, aset.model_id,
    )
    return aset
