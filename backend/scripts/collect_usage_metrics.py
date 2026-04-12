from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


backend_root = _backend_root()
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

get_arangodb_connection = None
config_module = None


def _load_backend_dependencies() -> None:
    global get_arangodb_connection
    global config_module

    if get_arangodb_connection is None:
        from core.dependencies import get_arangodb_connection as arango_connection

        get_arangodb_connection = arango_connection

    if config_module is None:
        from core import config as _config
        config_module = _config


def _safe_collection_count(db, name: str) -> int:
    if not db.has_collection(name):
        return 0
    return int(db.collection(name).count())


def collect_usage_metrics() -> dict[str, int]:
    _load_backend_dependencies()

    arango: Any = get_arangodb_connection(
        host=config_module.ARANGO_HOST,
        port=config_module.ARANGO_PORT,
        username=config_module.ARANGO_USERNAME,
        password=config_module.ARANGO_PASSWORD,
        db_name=config_module.ARANGO_DATABASE,
    )

    return {
        "users_total": _safe_collection_count(arango, "people"),
        "workspaces_total": _safe_collection_count(arango, "workspaces"),
        "workspace_artifacts_total": _safe_collection_count(arango, "workspace_artifacts"),
        "collections_total": _safe_collection_count(arango, "collections"),
        "committed_artifact_versions_total": _safe_collection_count(arango, "artifact_versions"),
        "grants_total": _safe_collection_count(arango, "grants"),
        "commits_total": _safe_collection_count(arango, "commits"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect local deployment usage metrics from ArangoDB."
    )
    parser.add_argument(
        "--output-file",
        default="/app/keys/usage-metrics.json",
        help="Path to write the collected usage metrics JSON.",
    )
    args = parser.parse_args()

    metrics = collect_usage_metrics()
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
