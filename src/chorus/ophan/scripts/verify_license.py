"""Operator script — verify an Agience license file against a distribution profile.

Usage (from the repo root):

    python -m chorus.ophan.scripts.verify_license /path/to/license.json \
        --profile managed-host

Lives in `chorus/ophan/scripts/` for the same reason as
`distribution_preflight.py` — licensing is Ophan's domain.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _ophan_dir() -> Path:
    return Path(__file__).resolve().parents[1]


_ophan_root = _ophan_dir()
if str(_ophan_root) not in sys.path:
    sys.path.insert(0, str(_ophan_root))


def main() -> int:
    import licensing  # noqa: E402 — sys.path adjusted above

    parser = argparse.ArgumentParser(description="Verify an Agience license file against a distribution profile.")
    parser.add_argument("license_file", help="Path to the signed license artifact JSON file.")
    parser.add_argument("--profile", required=True, help="Distribution profile name to evaluate.")
    args = parser.parse_args()

    payload = json.loads(Path(args.license_file).read_text(encoding="utf-8"))
    result = licensing.preflight_license(args.profile, payload)

    print(json.dumps(result.model_dump(), indent=2))
    return 0 if result.verification.valid and result.compatibility.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
