from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


backend_root = _backend_root()
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _maybe_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _compute_overages(usage: dict[str, Any], allowances: dict[str, Any]) -> dict[str, Any]:
    overages: dict[str, Any] = {}
    for key, allowance_value in allowances.items():
        usage_value = usage.get(key)
        usage_number = _coerce_number(usage_value)
        allowance_number = _coerce_number(allowance_value)
        if usage_number is None or allowance_number is None or usage_number <= allowance_number:
            continue
        overages[key] = {
            "used": usage_number,
            "allowed": allowance_number,
            "over": usage_number - allowance_number,
        }
    return overages


def _reporting_period(start: str | None, end: str | None, label: str | None) -> dict[str, Any] | None:
    payload = {
        "start": start,
        "end": end,
        "label": label,
    }
    filtered = {key: value for key, value in payload.items() if value}
    return filtered or None


def main() -> int:
    from scripts.review_installation import _read_json_file  # type: ignore[import-not-found]

    parser = argparse.ArgumentParser(
        description="Generate a canonical licensing usage snapshot JSON payload for Ophan reporting."
    )
    parser.add_argument("--usage-file", required=True, help="Path to the measured usage JSON object.")
    parser.add_argument("--allowances-file", help="Optional path to the allowance JSON object.")
    parser.add_argument("--license-file", default=os.getenv("LICENSING_LICENSE_FILE", "/app/keys/license.json"), help="Path to the signed license artifact JSON file.")
    parser.add_argument("--state-file", default=os.getenv("LICENSING_REVIEW_STATE_FILE", "/app/keys/installation-review.json"), help="Path to the saved installation review JSON file.")
    parser.add_argument("--output-file", default=os.getenv("LICENSING_USAGE_SNAPSHOT_FILE", "/app/keys/usage-snapshot.json"), help="Path to write the generated usage snapshot JSON.")
    parser.add_argument("--captured-at", help="Optional ISO 8601 capture timestamp.")
    parser.add_argument("--period-start", help="Optional ISO 8601 period start.")
    parser.add_argument("--period-end", help="Optional ISO 8601 period end.")
    parser.add_argument("--period-label", help="Optional human-readable period label, for example 2026-03.")
    parser.add_argument("--usage-id", help="Optional usage snapshot identifier.")
    args = parser.parse_args()

    usage = _read_json_file(Path(args.usage_file))
    if not usage:
        raise RuntimeError("Usage file must contain a JSON object.")

    allowances = _read_json_file(Path(args.allowances_file)) if args.allowances_file else {}
    license_payload = _read_json_file(Path(args.license_file))
    state_payload = _read_json_file(Path(args.state_file))

    usage_id = args.usage_id or f"usage_{uuid4().hex[:12]}"
    captured_at = args.captured_at or _now_iso()
    product = _maybe_dict(license_payload, "product")

    snapshot = {
        "schema_version": "1",
        "usage_id": usage_id,
        "account_id": license_payload.get("account_id") or state_payload.get("account_id"),
        "license_id": license_payload.get("license_id") or state_payload.get("license_id"),
        "install_id": state_payload.get("install_id"),
        "profile": state_payload.get("profile") or (product.get("distribution_profiles") or [None])[0],
        "runtime_role": state_payload.get("runtime_role") or (product.get("runtime_roles") or [None])[0],
        "captured_at": captured_at,
        "reporting_period": _reporting_period(args.period_start, args.period_end, args.period_label),
        "usage": usage,
        "allowances": allowances,
        "overages": _compute_overages(usage, allowances),
        "state": "recorded",
    }
    snapshot = {key: value for key, value in snapshot.items() if value is not None}

    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())