"""Long-term embeddings cache (SQLite) — keyed by ``(model_id, sha256(text))``.

We run / test / rebuild a lot and the embedder is a paid GPU; this avoids
re-embedding the same texts (seeds, reindex, repeated queries) across runs,
rebuilds, and restarts. Persisted under the data dir so it survives process
restarts and image rebuilds (when the data volume is mounted).

Disable with ``EMBEDDINGS_CACHE=0``. Path via ``EMBEDDINGS_CACHE_PATH``
(default ``<BASE_DIR>/.data/mantle/embeddings_cache.sqlite``).

Vectors are stored as little-endian float32 blobs. Empty/None vectors are never
cached, so a degraded (unconfigured-provider) run does not poison the cache.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import struct
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class EmbeddingsCache:
    """SQLite-backed cache of text → embedding vector, namespaced by model id."""

    def __init__(self, path: str | os.PathLike) -> None:
        self._path = str(path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS embeddings "
                "(k TEXT PRIMARY KEY, dim INTEGER NOT NULL, vec BLOB NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30.0)
        # WAL keeps concurrent readers (search) from blocking the writer (ingest).
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            pass
        return conn

    @staticmethod
    def _key(model_id: str, text: str) -> str:
        h = hashlib.sha256()
        h.update((model_id or "").encode("utf-8"))
        h.update(b"\x00")
        h.update(text.encode("utf-8"))
        return h.hexdigest()

    def get_many(self, model_id: str, texts: List[str]) -> List[Optional[List[float]]]:
        """Return cached vectors aligned 1:1 with ``texts`` (``None`` on miss)."""
        if not texts:
            return []
        keys = [self._key(model_id, t) for t in texts]
        found: dict[str, List[float]] = {}
        uniq = list(dict.fromkeys(keys))
        with self._connect() as conn:
            for i in range(0, len(uniq), 500):  # stay under SQLite's variable limit
                batch = uniq[i:i + 500]
                placeholders = ",".join("?" * len(batch))
                rows = conn.execute(
                    f"SELECT k, dim, vec FROM embeddings WHERE k IN ({placeholders})",
                    batch,
                )
                for k, dim, blob in rows:
                    found[k] = list(struct.unpack(f"<{int(dim)}f", blob))
        return [found.get(k) for k in keys]

    def put_many(
        self,
        model_id: str,
        texts: List[str],
        vectors: List[Optional[List[float]]],
    ) -> int:
        """Cache non-empty vectors. Returns the number of rows written."""
        rows = []
        for text, vec in zip(texts, vectors):
            if not vec:
                continue
            v = [float(x) for x in vec]
            rows.append((self._key(model_id, text), len(v), struct.pack(f"<{len(v)}f", *v)))
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO embeddings (k, dim, vec) VALUES (?, ?, ?)", rows
            )
        return len(rows)

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])
