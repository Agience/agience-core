"""Tests for `search.mantle.stores` (Step 2.2b.iii).

In-memory store implementation. Crypto correctness is covered in
test_mantle_indexer.py.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from search.mantle.stores import InMemoryCellStore


# ---------------------------------------------------------------------------
# InMemoryCellStore
# ---------------------------------------------------------------------------

class TestInMemoryCellStore:
    def test_put_get_round_trip(self):
        store = InMemoryCellStore()
        store.put("o-1", "col-A", b"blob-a")
        assert store.get("o-1", "col-A") == b"blob-a"

    def test_get_missing_returns_none(self):
        store = InMemoryCellStore()
        assert store.get("o-1", "col-A") is None

    def test_overwrite(self):
        store = InMemoryCellStore()
        store.put("o-1", "col-A", b"v1")
        store.put("o-1", "col-A", b"v2")
        assert store.get("o-1", "col-A") == b"v2"

    def test_delete(self):
        store = InMemoryCellStore()
        store.put("o-1", "col-A", b"x")
        store.delete("o-1", "col-A")
        assert store.get("o-1", "col-A") is None

    def test_delete_missing_is_no_op(self):
        store = InMemoryCellStore()
        store.delete("o-1", "col-A")  # no exception

    def test_list_cells_partitioned_by_owner(self):
        store = InMemoryCellStore()
        store.put("o-1", "col-A", b"x")
        store.put("o-1", "col-B", b"y")
        store.put("o-2", "col-A", b"q")
        cells_o1 = store.list_cells("o-1")
        cells_o2 = store.list_cells("o-2")
        assert set(cells_o1) == {"col-A", "col-B"}
        assert set(cells_o2) == {"col-A"}

    def test_thread_safety(self):
        """Many concurrent writers don't lose updates."""
        store = InMemoryCellStore()
        n = 100

        def writer(i: int):
            store.put("o-1", f"col-{i}", f"blob-{i}".encode())

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(writer, range(n)))

        assert len(store.list_cells("o-1")) == n
        for i in (0, 50, 99):
            assert store.get("o-1", f"col-{i}") == f"blob-{i}".encode()
