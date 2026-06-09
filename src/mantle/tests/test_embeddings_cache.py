"""Long-term embeddings cache (SQLite) + the cached Embeddings facade."""

import pytest

from kernel.embeddings_cache import EmbeddingsCache


def test_cache_roundtrip_and_namespacing(tmp_path):
    c = EmbeddingsCache(str(tmp_path / "c.sqlite"))
    assert c.get_many("m1", ["a", "b"]) == [None, None]

    assert c.put_many("m1", ["a", "b"], [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]) == 2
    got = c.get_many("m1", ["a", "c", "b"])
    assert got[1] is None                                  # 'c' is a miss
    assert got[0] == pytest.approx([0.1, 0.2, 0.3], abs=1e-6)
    assert got[2] == pytest.approx([0.4, 0.5, 0.6], abs=1e-6)

    assert c.get_many("m2", ["a"]) == [None]               # model-namespaced
    assert c.put_many("m1", ["x"], [[]]) == 0              # empties not cached
    assert c.count() == 2


def test_embeddings_facade_caches(tmp_path, monkeypatch):
    import kernel.embeddings as E

    monkeypatch.setenv("EMBEDDINGS_CACHE", "1")
    monkeypatch.setenv("EMBEDDINGS_CACHE_PATH", str(tmp_path / "facade.sqlite"))

    calls = {"n": 0, "texts": []}

    def stub(texts):
        calls["n"] += 1
        calls["texts"].extend(texts)
        return [[float(len(t)), 1.0] for t in texts]

    monkeypatch.setattr(E, "_build_provider", lambda: stub)
    E.reset_provider()  # also resets the cache singleton so the tmp path loads
    emb = E.Embeddings()

    r1 = emb(["hello", "world"])
    assert r1[0] == [5.0, 1.0] and calls["n"] == 1

    r2 = emb(["hello", "world"])          # all cached → provider NOT called again
    assert calls["n"] == 1
    assert r2[0] == pytest.approx([5.0, 1.0], abs=1e-6)

    before = calls["n"]
    emb(["hello", "new"])                 # only the miss is embedded
    assert calls["n"] == before + 1
    assert calls["texts"][-1] == "new"

    E.reset_provider()
