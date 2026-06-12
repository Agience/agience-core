"""Anchors & reconciliation — the geometry layer.

The AnchorSet is the shared coordinate system / routing centroids / grounding
(see `internal design notes` §3–§4). The Reconciler
turns any source embedding into the native language: a sparse, model-unbiased
anchor-relative code.

INVARIANT (§1): this layer operates on plaintext vectors only. It never touches
cell keys, the light-cone, the oracle, or the ledger, and runs strictly before
partition/encryption (index) and routing (query). It cannot affect authorization.
"""

from .activate import activate_vector
from .anchorset import (
    Anchor, AnchorSet, L0, L1, L2, CANDIDATE, WORKING, CANONICAL,
)
from .bootstrap import bootstrap_anchorset, gather_seed_corpus
from .crosswalk import Crosswalk, CrosswalkRegistry, fit_crosswalk
from .density import DensityZoom
from .grow import propose_anchor
from .reconciler import Reconciler, SparseCode
from .routing import route_query, route_vector
from .repo import AnchorRepo, ArangoAnchorRepo, InMemoryAnchorRepo
from .store import (
    get_anchor_repo,
    get_crosswalks,
    get_density_zoom,
    get_live_anchorset,
    require_live_anchorset,
    reset_anchorset,
    save_live_anchorset,
    set_anchor_repo,
)

__all__ = [
    "activate_vector", "propose_anchor",
    "Anchor", "AnchorSet", "Reconciler", "SparseCode", "DensityZoom",
    "Crosswalk", "CrosswalkRegistry", "fit_crosswalk",
    "L0", "L1", "L2", "CANDIDATE", "WORKING", "CANONICAL",
    "route_query", "route_vector",
    "bootstrap_anchorset", "gather_seed_corpus",
    "AnchorRepo", "ArangoAnchorRepo", "InMemoryAnchorRepo",
    "get_anchor_repo", "set_anchor_repo",
    "get_live_anchorset", "require_live_anchorset",
    "get_density_zoom", "get_crosswalks",
    "save_live_anchorset", "reset_anchorset",
]
