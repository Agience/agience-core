from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deployment-mode-aware licensing preflight for a distribution profile."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["dev", "self-host", "cloud-host"],
        help="Deployment mode being prepared.",
    )
    parser.add_argument("--profile", required=True, help="Distribution profile name to evaluate.")
    parser.add_argument(
        "--license-file",
        help="Optional signed license artifact JSON. Required for profiles that resolve to a signed commercial license.",
    )
    parser.add_argument(
        "--trust-anchors",
        help="Optional path to licensing trust anchors JSON. Defaults to LICENSING_PUBLIC_KEYS_PATH if set.",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    trust_anchor_path = args.trust_anchors or os.getenv("LICENSING_PUBLIC_KEYS_PATH")
    if trust_anchor_path:
        os.environ["LICENSING_PUBLIC_KEYS_PATH"] = trust_anchor_path

    from services import licensing_service  # pylint: disable=import-outside-toplevel

    payload = None
    if args.license_file:
        payload = json.loads(Path(args.license_file).read_text(encoding="utf-8"))

    result = licensing_service.preflight_deployment_mode(args.mode, args.profile, payload)
    print(json.dumps(result.model_dump(), indent=2))
    return 0 if result.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())