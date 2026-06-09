"""Activate verb — the geometry core (activate_vector) + POST /artifacts/activate."""

import numpy as np
import pytest

from search.anchors import AnchorSet, store
from search.anchors.activate import activate_vector
from search.anchors.anchorset import l2norm
from search.anchors.repo import InMemoryAnchorRepo

D = 8


@pytest.fixture(autouse=True)
def _restore_repo():
    """Restore the default (Arango) AnchorRepo after each test."""
    yield
    store.set_anchor_repo(None)


def _live_anchorset():
    store.set_anchor_repo(InMemoryAnchorRepo())
    aset = AnchorSet("hf:test@1.0", D)
    base = l2norm(np.arange(1, D + 1, dtype=np.float32))
    aset.add_text("alpha", base)
    aset.add_text("beta", l2norm(np.ones(D, dtype=np.float32)))
    aset.add_text("gamma", l2norm(np.eye(D)[3]))
    store.save_live_anchorset(aset)
    return base


def test_activate_vector_geometry():
    base = _live_anchorset()
    a = activate_vector(l2norm(base + 0.01 * np.ones(D, dtype=np.float32)), top_anchors=2)
    assert a["model_id"] == "hf:test@1.0"
    assert a["anchors"][0]["label"] == "alpha"        # nearest grounded concept
    assert a["density"] is not None and a["density"]["layer"] in ("L0", "L1", "L2")
    assert isinstance(a["novel"], bool)


def test_activate_vector_no_anchorset():
    store.set_anchor_repo(InMemoryAnchorRepo())       # empty → no live AnchorSet
    a = activate_vector([0.1] * D)
    assert a == {"model_id": None, "anchors": [], "density": None, "novel": False}


@pytest.mark.asyncio
async def test_activate_route(client):
    base = _live_anchorset()
    emb = l2norm(base + 0.01 * np.ones(D, dtype=np.float32)).tolist()

    resp = await client.post(
        "/artifacts/activate",
        json={"embedding": emb, "act": False, "top_anchors": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["activation"]["model_id"] == "hf:test@1.0"
    assert "alpha" in [x["label"] for x in data["activation"]["anchors"]]
    assert data["activation"]["density"] is not None
    assert data["neighbors"] == []

    # must provide exactly one of text/embedding
    bad = await client.post("/artifacts/activate", json={"text": "x", "embedding": emb})
    assert bad.status_code == 400
