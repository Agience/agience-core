"""AnchorSet + Reconciler — the native-language geometry layer.

Validates the load-bearing claim of the canonical plan (§4): the anchor-relative
code is **model-unbiased** — a gauge change (rotation = "a different embedding
model") leaves the native code unchanged.
"""

import numpy as np
import pytest

from search.anchors import AnchorSet, Reconciler
from search.anchors import store as _store
from search.anchors.anchorset import l2norm
from search.anchors.repo import InMemoryAnchorRepo

D = 32


@pytest.fixture
def anchor_repo():
    """Inject an in-memory AnchorRepo as the live store (anchors are artifacts;
    this keeps the geometry tests db-free), restoring the default repo after."""
    repo = InMemoryAnchorRepo()
    _store.set_anchor_repo(repo)
    try:
        yield repo
    finally:
        _store.set_anchor_repo(None)


def _clusters(rng, n_clusters=4, per=40, d=D, spread=0.12):
    centers = l2norm(rng.standard_normal((n_clusters, d)).astype(np.float32))
    items, truth = [], []
    for c in range(n_clusters):
        pts = l2norm(centers[c] + spread * rng.standard_normal((per, d)).astype(np.float32))
        for j in range(per):
            items.append((f"c{c}_{j}", pts[j]))
            truth.append(c)
    return items, truth


def test_bootstrap_admits_real_medoids():
    rng = np.random.default_rng(7)
    items, _ = _clusters(rng)
    aset = AnchorSet(model_id="hf:test@1.0", dim=D).bootstrap(items, k=4, seed=0)
    assert len(aset) == 4
    labelset = {lab for lab, _ in items}
    # anchors are REAL items (fully-disclosed artifacts), not synthetic centers
    assert all(a.label in labelset for a in aset.anchors)


def test_routing_lands_in_own_cluster():
    rng = np.random.default_rng(7)
    items, truth = _clusters(rng)
    aset = AnchorSet("hf:test@1.0", D).bootstrap(items, k=4, seed=0)
    rec = Reconciler(aset, top_m=4)
    label_by_id = {a.anchor_id: a.label for a in aset.anchors}
    correct = 0
    for (_, vec), c in zip(items, truth):
        code = rec.to_native(vec)
        top_cluster = label_by_id[code.top_anchor_id].split("_")[0]
        correct += int(top_cluster == f"c{c}")
    assert correct / len(items) > 0.9


def test_same_cluster_more_similar_than_cross():
    rng = np.random.default_rng(3)
    items, truth = _clusters(rng)
    aset = AnchorSet("hf:test@1.0", D).bootstrap(items, k=4, seed=0)
    rec = Reconciler(aset, top_m=4)
    codes = [rec.to_native(v) for _, v in items]
    same = [i for i, c in enumerate(truth) if c == truth[0]]
    diff = [i for i, c in enumerate(truth) if c != truth[0]]
    s = codes[same[0]].dot(codes[same[1]])
    d = codes[same[0]].dot(codes[diff[0]])
    assert s > d


def test_native_code_is_model_invariant_under_gauge_change():
    """The core option-B claim: rotate the space (a different 'model'),
    re-derive anchors from the same items, and the native code is unchanged."""
    rng = np.random.default_rng(11)
    items, _ = _clusters(rng, n_clusters=4, per=30)
    labels = [lab for lab, _ in items]
    X = l2norm(np.vstack([v for _, v in items]))

    R, _ = np.linalg.qr(rng.standard_normal((D, D)))   # random orthogonal gauge
    Xr = (X @ R).astype(np.float32)

    A = AnchorSet("hf:m1@1.0", D).bootstrap(list(zip(labels, X)), k=4, seed=0)
    B = AnchorSet("hf:m2@1.0", D).bootstrap(list(zip(labels, Xr)), k=4, seed=0)
    recA, recB = Reconciler(A, top_m=4), Reconciler(B, top_m=4)

    for i in range(0, len(items), 7):
        ca = recA.to_native(X[i], model_id="hf:m1@1.0")
        cb = recB.to_native(Xr[i], model_id="hf:m2@1.0")
        la = sorted((A.anchors[int(p)].label, round(float(w), 4)) for p, w in zip(ca.indices, ca.weights))
        lb = sorted((B.anchors[int(p)].label, round(float(w), 4)) for p, w in zip(cb.indices, cb.weights))
        assert la == lb


def test_cross_model_without_crosswalk_fails_loudly():
    aset = AnchorSet("hf:m1@1.0", D)
    aset.add_text("a", l2norm(np.ones(D, dtype=np.float32)))
    rec = Reconciler(aset)
    try:
        rec.to_native(np.ones(D, dtype=np.float32), model_id="hf:other@1.0")
        assert False, "expected cross-walk error"
    except ValueError as exc:
        assert "cross-walk" in str(exc)


def test_sparsecode_dict_roundtrip():
    from search.anchors.reconciler import SparseCode

    rng = np.random.default_rng(1)
    items, _ = _clusters(rng, n_clusters=3, per=20)
    aset = AnchorSet("hf:test@1.0", D).bootstrap(items, k=3, seed=0)
    code = Reconciler(aset, top_m=3).to_native(items[0][1])
    back = SparseCode.from_dict(code.to_dict())
    assert list(back.indices) == list(code.indices)
    assert back.anchor_ids == code.anchor_ids
    assert back.dim == code.dim
    assert abs(back.dot(code) - 1.0) < 1e-5  # unit-norm code, self-cosine ~ 1


def test_store_roundtrip(anchor_repo):
    from search.anchors import store

    rng = np.random.default_rng(2)
    items, _ = _clusters(rng, n_clusters=4, per=20)
    aset = AnchorSet("hf:bge-m3@1.0", D).bootstrap(items, k=4, seed=0)
    store.save_live_anchorset(aset)             # persists each anchor via the repo

    loaded = store.get_live_anchorset()
    assert loaded is not None
    assert len(loaded) == len(aset)
    assert loaded.model_id == aset.model_id
    assert loaded.dim == aset.dim
    # a loaded anchor reconciles identically to the original
    a = Reconciler(aset, top_m=4).to_native(items[0][1])
    b = Reconciler(loaded, top_m=4).to_native(items[0][1])
    assert abs(a.dot(b) - 1.0) < 1e-5


def test_require_live_anchorset_autobootstraps(anchor_repo, monkeypatch):
    """One path: require_live_anchorset never returns None — it light-trains the
    set from the seed corpus on first use and persists it (as anchor artifacts)."""
    from search.anchors import bootstrap as bootstrap_mod
    from search.anchors import store

    assert store.get_live_anchorset() is None      # nothing bootstrapped yet

    fake = AnchorSet("hf:test@1.0", 8)
    fake.add_text("seed-anchor", l2norm(np.eye(8)[0]))

    def fake_bootstrap(repo=None, **_):
        if repo is not None:
            repo.bulk_add(fake.anchors)            # persist like the real bootstrap
        return fake

    monkeypatch.setattr(bootstrap_mod, "bootstrap_anchorset", fake_bootstrap)

    got = store.require_live_anchorset()
    assert got is not None and len(got) == 1       # auto-bootstrapped
    assert store.get_live_anchorset() is not None  # persisted + cached


def test_model_id_is_commons_format():
    from kernel.embeddings import model_id

    mid = model_id()
    assert mid.count("@") == 1 and ":" in mid  # <ns>:<path>@<ver>


def test_bootstrap_corpus_finds_platform_seeds():
    import manage_anchors

    corpus = manage_anchors.gather_seed_corpus()
    # the platform seed tree has 40+ artifacts (agents, servers, tools, docs)
    assert len(corpus) >= 20
    assert all(text for _, text in corpus)


# --------------------------------------------------------------------------
# P2 — anchor routing + cluster-aware cells
# --------------------------------------------------------------------------

def test_route_vector_and_query():
    from search.anchors import routing

    rng = np.random.default_rng(5)
    items, _ = _clusters(rng, n_clusters=4, per=25)
    aset = AnchorSet("hf:test@1.0", D).bootstrap(items, k=4, seed=0)

    cid = routing.route_vector(aset, items[0][1])
    assert cid in {a.anchor_id for a in aset.anchors}

    cands = routing.route_query(aset, items[0][1], nprobe=3)
    assert len(cands) == 3
    assert cands[0] == cid          # the index cell is the top query candidate
    assert cands[0] != cands[1]

    # One path: a vector that can't be placed (wrong dimension) is an error,
    # not a flat fallback.
    import pytest
    with pytest.raises(ValueError):
        routing.route_vector(aset, np.ones(D + 1, dtype=np.float32))
    with pytest.raises(ValueError):
        routing.route_query(aset, np.ones(D + 1, dtype=np.float32))


def test_oracle_cluster_keying_separates_anchors():
    from cryptography.fernet import Fernet

    from search.mantle.oracle import FernetMasterKeyStore, OracleService

    svc = OracleService(FernetMasterKeyStore(Fernet(Fernet.generate_key())))
    # One formula: info = collection ‖ 0x00 ‖ cluster. Each routing anchor gets
    # an independent key; re-derivation is deterministic. There is no flat key.
    anchor_x = svc.derive_cell_key("owner1", "colA", "anchorX")
    anchor_x2 = svc.derive_cell_key("owner1", "colA", "anchorX")
    anchor_y = svc.derive_cell_key("owner1", "colA", "anchorY")

    assert anchor_x == anchor_x2                 # deterministic per (owner, col, anchor)
    assert anchor_x != anchor_y                  # per-anchor cells are independent
    assert len({len(k) for k in (anchor_x, anchor_y)}) == 1 and len(anchor_x) == 32


def test_cell_aad_binding():
    from search.mantle.cell import cell_aad

    # One formula: AAD = "collection:cluster" (canonical plan §5.1).
    assert cell_aad("colA", "anchorX") == "colA:anchorX"
    assert cell_aad("colA", "anchorY") == "colA:anchorY"


def test_cell_store_is_cluster_aware():
    from search.mantle.stores import InMemoryCellStore

    s = InMemoryCellStore()
    s.put("o", "c", b"a1", "anchorX")
    s.put("o", "c", b"a2", "anchorY")
    s.put("o", "c2", b"a3", "anchorX")

    assert s.get("o", "c", "anchorX") == b"a1"
    assert s.get("o", "c", "anchorY") == b"a2"
    assert s.get("o", "c", "missing") is None

    assert set(s.list_cells("o")) == {"c", "c2"}                  # distinct collections
    assert set(s.list_clusters("o", "c")) == {"anchorX", "anchorY"}

    s.delete("o", "c", "anchorX")
    assert s.get("o", "c", "anchorX") is None
    assert s.get("o", "c", "anchorY") == b"a2"   # deleting one cluster leaves others


def test_anchor_routing_end_to_end(anchor_repo):
    """P2.2: chunks land in per-anchor cells; a query routes to the right cell."""
    from cryptography.fernet import Fernet

    from search.anchors import store
    from search.mantle.engine import MantleQueryEngine
    from search.mantle.indexer import MantleIndexer
    from search.mantle.oracle import FernetMasterKeyStore, OracleService
    from search.mantle.stores import InMemoryCellStore

    d = 8
    e0, e1, e2 = (l2norm(np.eye(d)[i]) for i in range(3))

    def near(base, i):
        v = base.copy()
        v[3] += 0.01 * i
        return l2norm(v).tolist()

    aset = AnchorSet("hf:test@1.0", d)
    a0 = aset.add_text("anchor0", e0)
    a1 = aset.add_text("anchor1", e1)
    a2 = aset.add_text("anchor2", e2)
    store.save_live_anchorset(aset)             # get_live_anchorset() now returns this

    oracle = OracleService(FernetMasterKeyStore(Fernet(Fernet.generate_key())))
    cells = InMemoryCellStore()
    indexer = MantleIndexer(oracle, cells)
    principal, coll = "principal1", "coll1"

    chunks = [
        {"artifact_id": "art1", "chunk_id": 0, "embedding": near(e0, 1)},
        {"artifact_id": "art1", "chunk_id": 1, "embedding": near(e0, 2)},
        {"artifact_id": "art2", "chunk_id": 0, "embedding": near(e1, 1)},
    ]
    touched = indexer.index_artifact(principal, coll, chunks)
    assert touched == 2                          # two anchor cells touched (a0, a1)

    clusters = set(cells.list_clusters(principal, coll))
    assert a0.anchor_id in clusters and a1.anchor_id in clusters
    assert "" not in clusters                    # nothing flat — all routed
    assert a2.anchor_id not in clusters
    assert {c["chunk_id"] for c in indexer.chunks_in_cell(principal, coll, a0.anchor_id)} == {0, 1}

    # Query near anchor0 with nprobe=1 → only a0's cell is searched.
    engine = MantleQueryEngine(oracle, cells, nprobe=1)
    ids = {h.artifact_id for h in engine.search(near(e0, 1), [(principal, coll)], top_k=10)}
    assert "art1" in ids and "art2" not in ids   # routing limited the search to the right cell

    # Removal strips from every cluster.
    assert indexer.remove_artifact(principal, coll, "art1") == 1
    assert indexer.chunks_in_cell(principal, coll, a0.anchor_id) == []


# --------------------------------------------------------------------------
# P3 — density-zoom
# (Manifold-structure analysis lives in the Beacon add-on, not in core.)
# --------------------------------------------------------------------------


def test_density_layer_common_vs_novel():
    from search.anchors.anchorset import l2norm
    from search.anchors.density import DensityZoom

    rng = np.random.default_rng(2)
    d = 16
    base = l2norm(rng.standard_normal(d))
    aset = AnchorSet("hf:t@1.0", d)
    for i in range(8):
        aset.add_text(f"a{i}", l2norm(base + 0.03 * rng.standard_normal(d)))
    dz = DensityZoom(aset)

    common = dz.layer(l2norm(base + 0.01 * rng.standard_normal(d)))   # at the cluster
    orth = rng.standard_normal(d)
    orth = l2norm(orth - (orth @ base) * base)                        # orthogonal → far
    novel = dz.layer(orth)

    assert common[0] == "L2"
    assert novel[0] == "L0"
    assert common[1] > novel[1]


def test_density_layer_frame_invariant():
    from search.anchors.anchorset import l2norm
    from search.anchors.density import DensityZoom

    rng = np.random.default_rng(4)
    d = 16
    pts = l2norm(rng.standard_normal((10, d)))
    a = AnchorSet("hf:m1@1.0", d)
    for i, p in enumerate(pts):
        a.add_text(f"a{i}", p)
    R, _ = np.linalg.qr(rng.standard_normal((d, d)))
    b = AnchorSet("hf:m2@1.0", d)
    for i, p in enumerate(pts):
        b.add_text(f"a{i}", l2norm(p @ R))

    q = l2norm(rng.standard_normal(d))
    la, da = DensityZoom(a).layer(q)
    lb, db = DensityZoom(b).layer(q @ R)
    assert la == lb and abs(da - db) < 1e-4


# --------------------------------------------------------------------------
# P4 — cross-walk / AlignmentRegistry
# --------------------------------------------------------------------------

def test_crosswalk_enables_cross_model_reconcile():
    from search.anchors.crosswalk import CrosswalkRegistry, fit_crosswalk

    rng = np.random.default_rng(7)
    d = 16
    items = l2norm(rng.standard_normal((30, d)))        # concepts in TARGET space
    R, _ = np.linalg.qr(rng.standard_normal((d, d)))    # SOURCE = TARGET gauge-rotated
    items_src = l2norm(items @ R)

    aset = AnchorSet("hf:target@1.0", d)
    for i in range(6):
        aset.add_text(f"a{i}", items[i])

    reg = CrosswalkRegistry()
    cw = reg.register(fit_crosswalk(
        items_src, items,
        source_model_id="hf:source@1.0", target_model_id="hf:target@1.0",
        method="procrustes",
    ))
    assert cw.method == "procrustes" and cw.error_bound < 1e-3

    rec_x = Reconciler(aset, top_m=4, crosswalks=reg)
    rec_t = Reconciler(aset, top_m=4)
    q = 10
    code_src = rec_x.to_native(items_src[q], model_id="hf:source@1.0")
    code_tgt = rec_t.to_native(items[q])
    assert code_src.dot(code_tgt) > 0.99          # cross-walked code ≈ native code

    # without a registry, a foreign model still fails loudly
    try:
        Reconciler(aset, top_m=4).to_native(items_src[q], model_id="hf:source@1.0")
        assert False, "expected cross-walk error"
    except ValueError as exc:
        assert "cross-walk" in str(exc)


def test_crosswalk_linear_cross_dimension():
    from search.anchors.crosswalk import fit_crosswalk

    rng = np.random.default_rng(2)
    n, d_in, d_out = 60, 12, 20
    src = l2norm(rng.standard_normal((n, d_in)))
    M = rng.standard_normal((d_in, d_out))
    tgt = l2norm(src @ M)

    cw = fit_crosswalk(src, tgt, source_model_id="a@1", target_model_id="b@1")
    assert cw.method == "linear" and (cw.dim_in, cw.dim_out) == (d_in, d_out)
    assert cw.error_bound < 0.05

    x = l2norm(rng.standard_normal(d_in))
    assert float(cw.apply(x) @ l2norm(x @ M)) > 0.95


# --------------------------------------------------------------------------
# Anchor growth (RG-flow) — the AnchorSet grows as the manifold grows
# --------------------------------------------------------------------------

def test_propose_anchor_admits_novel_rejects_covered(anchor_repo):
    from search.anchors import store
    from search.anchors.anchorset import CANDIDATE
    from search.anchors.grow import propose_anchor

    d = 8
    base = l2norm(np.eye(d)[0])
    aset = AnchorSet("hf:t@1.0", d)
    for i in range(5):
        aset.add_text(f"a{i}", l2norm(base + 0.02 * np.random.default_rng(i).standard_normal(d)))
    store.save_live_anchorset(aset)
    before = len(store.get_live_anchorset())

    # a novel (orthogonal) signal in an uncovered region → admitted as CANDIDATE
    grown = propose_anchor("novel-concept", l2norm(np.eye(d)[4]))
    assert grown is not None and grown.tier == CANDIDATE
    assert len(store.get_live_anchorset()) == before + 1

    # a near-duplicate of the existing cluster → already covered → rejected
    assert propose_anchor("dup", l2norm(base + 0.001 * np.ones(d, dtype=np.float32))) is None
    assert len(store.get_live_anchorset()) == before + 1


def test_propose_anchor_no_anchorset_is_noop(anchor_repo):
    from search.anchors.grow import propose_anchor

    # Empty repo → no live AnchorSet → propose is a no-op.
    assert propose_anchor("x", [0.1] * 8) is None
