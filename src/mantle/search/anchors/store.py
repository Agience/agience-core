"""Live AnchorSet store — load from the artifact-backed repo + process cache.

The AnchorSet is a **collection of anchor artifacts** (see :mod:`.repo`). This
module is the process-level cache + lifecycle around it:

- :func:`require_live_anchorset` — mandatory accessor for the index/query path;
  bootstraps (light-trains) from the seed corpus on first use; never ``None``.
- :func:`get_live_anchorset` — read-only accessor (inspect / density / activate);
  may return ``None`` before the first bootstrap.

The AnchorSet is loaded by a DIRECT, non-authorizing read (canonical plan §1:
public geometry — no cell keys, no light-cone, no ledger).
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from .anchorset import AnchorSet
from .repo import AnchorRepo

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_cache: Optional[AnchorSet] = None
_loaded = False
_density_zoom = None          # DensityZoom | None — derived from the live AnchorSet
_dz_loaded = False
_repo_override: Optional[AnchorRepo] = None   # tests inject an InMemoryAnchorRepo


def get_anchor_repo() -> AnchorRepo:
    """The active :class:`AnchorRepo` — an injected one (tests) or the
    production Arango-backed repo over the current request DB handle."""
    if _repo_override is not None:
        return _repo_override
    from services.dependencies import get_arango_db
    from .repo import ArangoAnchorRepo
    return ArangoAnchorRepo(next(get_arango_db()))


def set_anchor_repo(repo: Optional[AnchorRepo]) -> None:
    """Inject the AnchorRepo (tests). Pass ``None`` to restore the default
    (Arango) repo. Resets the AnchorSet-derived caches."""
    global _repo_override
    with _lock:
        _repo_override = repo
    reset_anchorset()


def get_live_anchorset() -> Optional[AnchorSet]:
    """Return the cached live AnchorSet, loading from the repo once.

    Read-only accessor for inspection / density / activation. Returns ``None``
    only before the first bootstrap. Index and query callers MUST use
    :func:`require_live_anchorset` instead — the routed path needs the set to
    exist and never has a flat fallback.
    """
    global _cache, _loaded
    if _loaded:
        return _cache
    with _lock:
        if _loaded:
            return _cache
        try:
            _cache = get_anchor_repo().load()
        except Exception:
            logger.warning("Failed to load AnchorSet from repo", exc_info=True)
            _cache = None
        if _cache is not None:
            logger.info(
                "Loaded live AnchorSet: %d anchors (%s)", len(_cache), _cache.model_id
            )
        _loaded = True
        return _cache


def save_live_anchorset(anchorset: AnchorSet) -> None:
    """Persist every anchor of ``anchorset`` through the repo, then refresh the
    cache. (Anchors are normally persisted at creation; this is the
    bulk/whole-set path used by admin tooling.)"""
    get_anchor_repo().bulk_add(anchorset.anchors)
    reset_anchorset()
    logger.info("Saved live AnchorSet: %d anchors", len(anchorset))


def require_live_anchorset() -> AnchorSet:
    """Return the live AnchorSet, bootstrapping it from the platform seed corpus
    on first use. Never returns ``None`` — the routed path is the only path.

    The first call on a fresh deployment performs the light-training bootstrap
    (embed the seed corpus, cluster into anchors, persist them as artifacts).
    Subsequent calls hit the process cache / repo. Raises if the set is absent
    and cannot be bootstrapped (no seed corpus or embeddings provider) — there is
    no flat fallback, so the caller surfaces the error rather than degrading.
    """
    aset = get_live_anchorset()
    if aset is not None and len(aset) > 0:
        return aset
    with _lock:
        aset = get_live_anchorset()
        if aset is not None and len(aset) > 0:
            return aset
        from .bootstrap import bootstrap_anchorset
        bootstrap_anchorset(get_anchor_repo())   # persists anchors as artifacts
        reset_anchorset()
        reloaded = get_live_anchorset()
        if reloaded is None or len(reloaded) == 0:
            raise RuntimeError("AnchorSet bootstrap produced no anchors")
        return reloaded


def get_density_zoom():
    """Cached :class:`DensityZoom` over the live AnchorSet (``None`` when none).

    Built once per AnchorSet load (the threshold fit is O(K²) in anchors).
    """
    global _density_zoom, _dz_loaded
    if _dz_loaded:
        return _density_zoom
    with _lock:
        if _dz_loaded:
            return _density_zoom
        aset = get_live_anchorset()
        if aset is None or len(aset) == 0:
            _density_zoom = None
        else:
            from .density import DensityZoom
            _density_zoom = DensityZoom(aset)
        _dz_loaded = True
        return _density_zoom


_crosswalks = None


def get_crosswalks():
    """Process-level :class:`CrosswalkRegistry` (the AlignmentRegistry, §4.3).

    Empty until models are registered; the single-embedder default needs no
    cross-walks, so reconcile of a same-model vector is a straight pass-through.
    """
    global _crosswalks
    if _crosswalks is None:
        from .crosswalk import CrosswalkRegistry
        _crosswalks = CrosswalkRegistry()
    return _crosswalks


def reset_anchorset() -> None:
    """Drop the AnchorSet-derived caches (admin reload / tests / after a
    bootstrap or grow). The cross-walk registry is model-level and is left
    intact."""
    global _cache, _loaded, _density_zoom, _dz_loaded
    with _lock:
        _cache = None
        _loaded = False
        _density_zoom = None
        _dz_loaded = False
