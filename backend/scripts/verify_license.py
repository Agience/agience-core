from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


backend_root = _backend_root()
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


def main() -> int:
    from services import licensing_service

    parser = argparse.ArgumentParser(description="Verify an Agience license file against a distribution profile.")
    parser.add_argument("license_file", help="Path to the signed license artifact JSON file.")
    parser.add_argument("--profile", required=True, help="Distribution profile name to evaluate.")
    args = parser.parse_args()

    payload = json.loads(Path(args.license_file).read_text(encoding="utf-8"))
    result = licensing_service.preflight_license(args.profile, payload)

    print(json.dumps(result.model_dump(), indent=2))
    return 0 if result.verification.valid and result.compatibility.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())