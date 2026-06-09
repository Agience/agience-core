#!/usr/bin/env python3
"""manage_anchors.py — bootstrap / inspect the live MANTLE AnchorSet.

The AnchorSet is the shared coordinate system / routing centroids / grounding
(see `.dev/features/mantle-canonical-architecture.md` §3). "Light-training"
bootstrap clusters the platform's *common grounded knowledge* — the platform
seed corpus — and admits representative items as the initial L1 anchors. The
set grows from there as the manifold grows.

Run from the `mantle/` directory.

Actions
-------
bootstrap   Embed the platform seed corpus, cluster into K anchors, save.
inspect     Show the current live AnchorSet (count, model, sample anchors).

Requires the embeddings provider to be configured + reachable (EMBEDDINGS_URI).
"""

import argparse
import logging

from search.anchors import (
    bootstrap_anchorset,
    gather_seed_corpus,
    get_anchor_repo,
    get_live_anchorset,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s  %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("manage_anchors")


def action_bootstrap(k: int, dry_run: bool) -> None:
    corpus = gather_seed_corpus()
    if not corpus:
        raise SystemExit("No seed corpus under package/seeds/platform/artifacts.")
    logger.info("Gathered %d seed items for anchor bootstrap.", len(corpus))
    if dry_run:
        logger.info("[DRY-RUN] Would embed %d items, admit K=%d anchors.", len(corpus), k)
        for label, _ in corpus[:12]:
            logger.info("  - %s", label)
        return

    try:
        aset = bootstrap_anchorset(get_anchor_repo(), k=k)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    logger.info(
        "Bootstrapped AnchorSet: %d anchors (model=%s) persisted as artifacts",
        len(aset), aset.model_id,
    )
    for a in aset.anchors[: min(len(aset), 12)]:
        logger.info("  anchor[%s] %s", a.tier, a.label)


def action_inspect(_dry_run: bool) -> None:
    aset = get_live_anchorset()
    if aset is None:
        logger.info("No live AnchorSet yet. Run: python manage_anchors.py --action bootstrap")
        return
    logger.info("Live AnchorSet: %d anchors, model=%s, dim=%d", len(aset), aset.model_id, aset.dim)
    logger.info("  (manifold analysis is available via the Beacon add-on)")
    for a in aset.anchors[: min(len(aset), 25)]:
        logger.info("  [%s] %s  (%s)", a.tier, a.label, a.anchor_id[:12])


def action_grow(text: str, dry_run: bool) -> None:
    """Admit a novel signal as a new CANDIDATE anchor (RG-flow growth)."""
    if not text:
        raise SystemExit("--text is required for grow")
    from kernel.embeddings import Embeddings
    vectors = Embeddings()([text])
    if not vectors or not vectors[0]:
        raise SystemExit("Embeddings provider unavailable — set EMBEDDINGS_URI.")
    if dry_run:
        from search.anchors import get_density_zoom
        dz = get_density_zoom()
        layer = dz.layer(vectors[0])[0] if dz is not None else "?"
        logger.info("[DRY-RUN] %r → density layer %s (admitted only if L0/novel)", text, layer)
        return
    from search.anchors.grow import propose_anchor
    anchor = propose_anchor(text[:80], vectors[0])
    if anchor is None:
        logger.info("Not admitted — no AnchorSet, dim mismatch, or already covered (not novel).")
    else:
        logger.info("Admitted candidate anchor: %s (%s)", anchor.label, anchor.anchor_id[:12])


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the MANTLE AnchorSet.")
    parser.add_argument("--action", choices=["bootstrap", "inspect", "grow"], required=True)
    parser.add_argument("--k", type=int, default=24, help="Anchors to admit (bootstrap).")
    parser.add_argument("--text", help="Text to grow a candidate anchor from (grow).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.action == "bootstrap":
        action_bootstrap(args.k, args.dry_run)
    elif args.action == "inspect":
        action_inspect(args.dry_run)
    elif args.action == "grow":
        action_grow(args.text, args.dry_run)


if __name__ == "__main__":
    main()
