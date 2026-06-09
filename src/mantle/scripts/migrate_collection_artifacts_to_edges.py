"""One-shot migration: rename Arango edge collection `collection_artifacts` → `edges`.

Phase F of the four-container architecture rollout. Run once per deployment
when upgrading past the rename. Idempotent: re-running on an already-migrated
deployment is a no-op.

Usage
-----
From the repo root, with Mantle's environment variables in scope (so the
script can connect to the same Arango instance Mantle uses):

    python mantle/scripts/migrate_collection_artifacts_to_edges.py

The script will:
  1. Connect to Arango using `core.config` settings (ARANGO_HOST, etc.).
  2. If `edges` already exists and `collection_artifacts` does not → no-op.
  3. If `edges` does not exist and `collection_artifacts` does → rename.
  4. If both exist → fail loudly. Operator must reconcile manually.
  5. Update graph definitions to reference `edges` instead.

Per the no-auto-repair rule: this is an explicit operator-run migration. The
schema initializer in `mantle/schemas/arango/initialize.py` will fail at
startup if it sees `collection_artifacts` without `edges` — pointing operators
back to this script.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("migrate_collection_artifacts_to_edges")

# Make Mantle's package imports resolve when run from repo root.
_MANTLE_DIR = Path(__file__).resolve().parent.parent
if str(_MANTLE_DIR) not in sys.path:
    sys.path.insert(0, str(_MANTLE_DIR))

# Avoid running migrations during import-time sanity checks.
os.environ.setdefault("MANTLE_SKIP_LIFESPAN_INIT", "1")


def _connect():
    """Connect using the same Arango config Mantle uses at runtime."""
    from arango import ArangoClient  # type: ignore[import-untyped]

    from kernel import config
    from kernel.key_manager import init_arango_password

    init_arango_password()
    config.load_bootstrap_settings()

    host = config.ARANGO_HOST
    port = config.ARANGO_PORT
    url = f"http://{host}:{port}"
    client = ArangoClient(hosts=url)
    sys_db = client.db("_system", username=config.ARANGO_USERNAME, password=config.ARANGO_PASSWORD)

    if not sys_db.has_database(config.ARANGO_DATABASE):
        log.error("Database %s not found; nothing to migrate", config.ARANGO_DATABASE)
        sys.exit(2)

    return client.db(
        config.ARANGO_DATABASE,
        username=config.ARANGO_USERNAME,
        password=config.ARANGO_PASSWORD,
    )


def _rebuild_graph(db) -> None:
    """Drop + recreate the `agience_graph` so its edge_definitions reference `edges`."""
    graph_name = "agience_graph"
    if db.has_graph(graph_name):
        db.delete_graph(graph_name, drop_collections=False)
        log.info("Dropped graph %s (will be recreated by Mantle on next start)", graph_name)
    # Mantle's `_create_graph` rebuilds it on startup with the canonical
    # `edges` edge collection — no need to recreate it here.


def _migrate(db) -> int:
    has_legacy = db.has_collection("collection_artifacts")
    has_canonical = db.has_collection("edges")

    if has_canonical and not has_legacy:
        log.info("Migration not needed: `edges` already exists, no legacy collection")
        return 0

    if not has_canonical and not has_legacy:
        log.info("Neither collection exists — fresh database, Mantle will create `edges` on startup")
        return 0

    if has_canonical and has_legacy:
        log.error(
            "Both `collection_artifacts` and `edges` exist. The two collections "
            "must be reconciled manually before this script can proceed. "
            "Inspect both and merge or drop the unused one."
        )
        return 1

    log.info("Renaming edge collection `collection_artifacts` → `edges` ...")
    legacy = db.collection("collection_artifacts")
    legacy.rename("edges")
    log.info("Renamed. Rebuilding graph definition ...")
    _rebuild_graph(db)
    log.info("Migration complete. Restart Mantle to pick up the new schema.")
    return 0


if __name__ == "__main__":
    db = _connect()
    sys.exit(_migrate(db))
