from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


backend_root = _backend_root()
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


def _account_id(license_payload: dict[str, Any], state_payload: dict[str, Any], usage_payload: dict[str, Any]) -> str | None:
    for candidate in (
        usage_payload.get("account_id"),
        state_payload.get("account_id"),
        license_payload.get("account_id"),
    ):
        if candidate:
            return str(candidate)
    return None


def _license_id(license_payload: dict[str, Any], state_payload: dict[str, Any], usage_payload: dict[str, Any], cli_value: str | None) -> str | None:
    for candidate in (
        cli_value,
        usage_payload.get("license_id"),
        state_payload.get("license_id"),
        license_payload.get("license_id"),
    ):
        if candidate:
            return str(candidate)
    return None


def main() -> int:
    from scripts.review_installation import _decode_tool_result, _read_json_file  # type: ignore[import-not-found]

    parser = argparse.ArgumentParser(
        description="Submit a licensing usage snapshot to Ophan and persist the reporting result locally."
    )
    parser.add_argument("--ophan-uri", required=True, help="Ophan MCP endpoint, for example https://api.example.com/ophan/mcp.")
    parser.add_argument("--operator-token", required=True, help="Bearer token used to authenticate the operator against Ophan.")
    parser.add_argument("--workspace-id", required=True, help="Licensing workspace ID inside the licensor's Agience environment.")
    parser.add_argument("--snapshot-file", required=True, help="Path to the usage snapshot JSON payload.")
    parser.add_argument("--snapshot-artifact-id", help="Optional upstream source artifact ID for the snapshot.")
    parser.add_argument("--license-id", help="Optional license identifier override.")
    parser.add_argument("--license-file", default="/app/keys/license.json", help="Path to the signed license artifact JSON file.")
    parser.add_argument("--state-file", default="/app/keys/installation-review.json", help="Path to the saved installation review JSON file.")
    parser.add_argument("--result-file", default=os.getenv("LICENSING_USAGE_RESULT_FILE", "/app/keys/usage-report-result.json"), help="Path to persist the result returned by Ophan.")
    args = parser.parse_args()

    license_payload = _read_json_file(Path(args.license_file))
    state_payload = _read_json_file(Path(args.state_file))
    snapshot_payload = _read_json_file(Path(args.snapshot_file))
    if not snapshot_payload:
        raise RuntimeError("Snapshot payload must be a JSON object.")

    account_id = _account_id(license_payload, state_payload, snapshot_payload)
    license_id = _license_id(license_payload, state_payload, snapshot_payload, args.license_id)

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "record_usage_snapshot",
            "arguments": {
                "workspace_id": args.workspace_id,
                "snapshot_artifact_id": args.snapshot_artifact_id,
                "snapshot_payload": json.dumps(snapshot_payload),
                "account_id": account_id,
                "license_id": license_id,
            },
        },
    }
    headers = {
        "Authorization": f"Bearer {args.operator_token}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60.0, headers=headers) as client:
        response = client.post(args.ophan_uri, json=request)
        response.raise_for_status()
        payload = response.json()

    if "error" in payload:
        raise RuntimeError(f"MCP error: {payload['error']}")

    result = _decode_tool_result(payload.get("result", {}))
    result_file = Path(args.result_file)
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())