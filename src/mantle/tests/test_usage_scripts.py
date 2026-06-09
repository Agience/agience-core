from __future__ import annotations

import json

from scripts import collect_usage_metrics, generate_usage_snapshot


class _ArangoCollectionStub:
    def __init__(self, count: int):
        self._count = count

    def count(self) -> int:
        return self._count


class _ArangoStub:
    def __init__(self, counts: dict[str, int]):
        self._counts = counts

    def has_collection(self, name: str) -> bool:
        return name in self._counts

    def collection(self, name: str) -> _ArangoCollectionStub:
        return _ArangoCollectionStub(self._counts[name])


def test_collect_usage_metrics_returns_stable_metric_set(monkeypatch):
    monkeypatch.setattr(
        collect_usage_metrics,
        "get_arangodb_connection",
        lambda **_kwargs: _ArangoStub(
            {
                "people": 12,
                "workspaces": 7,
                "workspace_artifacts": 345,
                "collections": 5,
                "artifact_versions": 22,
                "grants": 4,
                "commits": 11,
            }
        ),
    )

    metrics = collect_usage_metrics.collect_usage_metrics()

    assert metrics == {
        "users_total": 12,
        "workspaces_total": 7,
        "workspace_artifacts_total": 345,
        "collections_total": 5,
        "committed_artifact_versions_total": 22,
        "grants_total": 4,
        "commits_total": 11,
    }


def test_generate_usage_snapshot_computes_overages_and_infers_ids(tmp_path):
    usage_file = tmp_path / "usage.json"
    allowances_file = tmp_path / "allowances.json"
    license_file = tmp_path / "license.json"
    state_file = tmp_path / "state.json"
    output_file = tmp_path / "snapshot.json"

    usage_file.write_text(json.dumps({"users_total": 12, "workspace_artifacts_total": 1200}), encoding="utf-8")
    allowances_file.write_text(json.dumps({"users_total": 10, "workspace_artifacts_total": 2000}), encoding="utf-8")
    license_file.write_text(
        json.dumps(
            {
                "license_id": "lic-123",
                "account_id": "acct-123",
                "product": {
                    "distribution_profiles": ["standard"],
                    "runtime_roles": ["standard"],
                },
            }
        ),
        encoding="utf-8",
    )
    state_file.write_text(json.dumps({"install_id": "inst-123"}), encoding="utf-8")

    # Drive the script through its argparse entrypoint semantics by patching argv.
    argv = [
        "generate_usage_snapshot.py",
        "--usage-file",
        str(usage_file),
        "--allowances-file",
        str(allowances_file),
        "--license-file",
        str(license_file),
        "--state-file",
        str(state_file),
        "--output-file",
        str(output_file),
        "--captured-at",
        "2026-03-07T12:00:00Z",
        "--period-label",
        "2026-03",
        "--usage-id",
        "usage-123",
    ]

    original_argv = generate_usage_snapshot.sys.argv
    generate_usage_snapshot.sys.argv = argv
    try:
        result = generate_usage_snapshot.main()
    finally:
        generate_usage_snapshot.sys.argv = original_argv

    assert result == 0
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["license_id"] == "lic-123"
    assert payload["account_id"] == "acct-123"
    assert payload["install_id"] == "inst-123"
    assert payload["profile"] == "standard"
    assert payload["runtime_role"] == "standard"
    assert payload["reporting_period"] == {"label": "2026-03"}
    assert payload["overages"] == {
        "users_total": {
            "used": 12.0,
            "allowed": 10.0,
            "over": 2.0,
        }
    }