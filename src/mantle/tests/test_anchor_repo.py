"""AnchorRepo — anchors persist + reload as artifacts.

Covers the in-memory repo (geometry tests stay db-free) and the Arango repo's
load/add against a minimal fake DB, proving an anchor round-trips through the
artifact form (``to_context`` / ``from_context``) with its id + embedding intact.
"""

from __future__ import annotations

import json

import numpy as np

from search.anchors.anchorset import Anchor, AnchorSet, l2norm
from search.anchors.repo import ArangoAnchorRepo, InMemoryAnchorRepo

D = 8


def _aset() -> AnchorSet:
    a = AnchorSet("hf:test@1.0", D)
    a.add_text("alpha", l2norm(np.eye(D)[0]))
    a.add_text("beta", l2norm(np.eye(D)[1]))
    return a


def test_anchor_id_is_deterministic_uuid():
    import uuid
    a1 = Anchor.make("x", l2norm(np.eye(D)[0]), "hf:test@1.0")
    a2 = Anchor.make("x", l2norm(np.eye(D)[0]), "hf:test@1.0")
    assert a1.anchor_id == a2.anchor_id            # content-addressed → stable id
    assert a1.content_hash == a2.content_hash
    uuid.UUID(a1.anchor_id)                         # a valid UUID (artifact id)
    assert a1.content_hash != a1.anchor_id          # hash vs derived uuid


def test_anchor_context_roundtrip():
    a = Anchor.make("alpha", l2norm(np.arange(1, D + 1, dtype=np.float32)), "hf:test@1.0")
    back = Anchor.from_context(a.anchor_id, a.to_context())
    assert back.anchor_id == a.anchor_id
    assert back.label == a.label and back.model_id == a.model_id
    assert back.content_hash == a.content_hash
    assert np.allclose(back.embedding, a.embedding, atol=1e-6)


def test_inmemory_repo_roundtrip():
    repo = InMemoryAnchorRepo()
    src = _aset()
    repo.bulk_add(src.anchors)
    assert repo.count() == 2
    loaded = repo.load()
    assert loaded is not None and len(loaded) == 2
    assert {a.anchor_id for a in loaded.anchors} == {a.anchor_id for a in src.anchors}


def test_inmemory_repo_empty_loads_none():
    assert InMemoryAnchorRepo().load() is None


# ---------------------------------------------------------------------------
# Arango repo against a minimal fake DB
# ---------------------------------------------------------------------------

class _FakeArtifacts:
    def __init__(self, store: dict):
        self._store = store

    def get(self, key):
        return self._store.get(key)


class _FakeDB:
    """Just enough of the Arango handle for ArangoAnchorRepo via the db.arango
    helpers we monkeypatch below."""
    def __init__(self):
        self.docs: dict = {}

    def collection(self, _name):
        return _FakeArtifacts(self.docs)


def test_arango_repo_add_and_load(monkeypatch):
    from db import arango as db_arango
    from services import platform_topology

    db = _FakeDB()
    edges = []

    # AnchorSet collection id resolves to a fixed value.
    monkeypatch.setattr(platform_topology, "get_id_optional", lambda slug: "anchorset-col")

    def fake_create_artifact(_db, entity):
        d = entity.to_dict()
        d["content_type"] = entity.content_type
        db.docs[entity.id] = d
        return entity

    def fake_get_artifact(_db, aid):
        return db.docs.get(aid)

    def fake_add_to_collection(_db, cid, root_id, **kw):
        edges.append((cid, root_id))
        return True

    def fake_list_collection_artifacts(_db, cid, **kw):
        return [d for d in db.docs.values() if d.get("collection_id") == cid]

    monkeypatch.setattr(db_arango, "create_artifact", fake_create_artifact)
    monkeypatch.setattr(db_arango, "get_artifact", fake_get_artifact)
    monkeypatch.setattr(db_arango, "add_artifact_to_collection", fake_add_to_collection)
    monkeypatch.setattr(db_arango, "list_collection_artifacts", fake_list_collection_artifacts)

    repo = ArangoAnchorRepo(db)
    src = _aset()
    repo.bulk_add(src.anchors)

    # each anchor became an artifact + a membership edge
    assert len(db.docs) == 2
    assert len(edges) == 2
    sample = next(iter(db.docs.values()))
    assert sample["content_type"] == "application/vnd.agience.anchor+json"
    assert json.loads(sample["context"])["embedding"]          # embedding persisted

    # idempotent: re-adding the same anchors creates no new docs
    repo.bulk_add(src.anchors)
    assert len(db.docs) == 2

    loaded = repo.load()
    assert loaded is not None and len(loaded) == 2
    assert {a.anchor_id for a in loaded.anchors} == {a.anchor_id for a in src.anchors}
    assert loaded.model_id == "hf:test@1.0" and loaded.dim == D
