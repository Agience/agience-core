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


def _read_json_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _distribution_profile(license_payload: dict[str, Any]) -> str | None:
    product = license_payload.get("product")
    if not isinstance(product, dict):
        return None
    profiles = product.get("distribution_profiles")
    if not isinstance(profiles, list):
        return None
    for item in profiles:
        if item:
            return str(item)
    return None


def _decode_tool_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured

        content = result.get("content")
        if isinstance(content, list):
            text_parts = [
                item.get("text")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            if text_parts:
                combined = "\n".join(text_parts)
                try:
                    parsed = json.loads(combined)
                except json.JSONDecodeError:
                    return {"raw_text": combined}
                return parsed if isinstance(parsed, dict) else {"value": parsed}

        return result

    if isinstance(result, str):
        parsed = json.loads(result)
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    raise RuntimeError("Unexpected MCP tool result shape.")


def _write_json_file(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review a licensed installation via Ophan and persist the activation lease locally."
    )
    parser.add_argument(
        "--ophan-uri",
        default=os.getenv("OPHAN_MCP_URI"),
        help="Ophan MCP endpoint, for example https://api.example.com/ophan/mcp.",
    )
    parser.add_argument(
        "--operator-token",
        default=os.getenv("AGIENCE_OPERATOR_TOKEN"),
        help="Bearer token used to authenticate the operator against Ophan.",
    )
    parser.add_argument(
        "--workspace-id",
        default=os.getenv("LICENSING_WORKSPACE_ID"),
        help="Licensing workspace ID inside the licensor's Agience environment.",
    )
    parser.add_argument(
        "--install-id",
        default=os.getenv("LICENSING_INSTALL_ID"),
        help="Stable installation identifier. Falls back to state-file contents when available.",
    )
    parser.add_argument(
        "--instance-id",
        default=os.getenv("LICENSING_INSTANCE_ID"),
        help="Optional runtime instance identifier.",
    )
    parser.add_argument(
        "--device-id",
        default=os.getenv("LICENSING_DEVICE_ID"),
        help="Optional hardware or node identifier.",
    )
    parser.add_argument(
        "--profile",
        help="Distribution profile. If omitted, inferred from the saved state or license file.",
    )
    parser.add_argument(
        "--license-id",
        help="License identifier. If omitted, inferred from the saved state or license file.",
    )
    parser.add_argument(
        "--license-file",
        default=os.getenv("LICENSING_LICENSE_FILE", "/app/keys/license.json"),
        help="Path to the signed license artifact JSON file.",
    )
    parser.add_argument(
        "--state-file",
        default=os.getenv("LICENSING_REVIEW_STATE_FILE", "/app/keys/installation-review.json"),
        help="Path to persist the review result and installation identity.",
    )
    parser.add_argument(
        "--lease-file",
        default=os.getenv("LICENSING_ACTIVATION_LEASE_FILE", "/app/keys/activation-lease.json"),
        help="Path to persist the activation lease when one is returned.",
    )
    parser.add_argument(
        "--require-activation-lease",
        action="store_true",
        help="Exit non-zero if Ophan does not return an activation lease.",
    )
    args = parser.parse_args()

    if not args.ophan_uri:
        parser.error("--ophan-uri or OPHAN_MCP_URI is required.")
    if not args.operator_token:
        parser.error("--operator-token or AGIENCE_OPERATOR_TOKEN is required.")
    if not args.workspace_id:
        parser.error("--workspace-id or LICENSING_WORKSPACE_ID is required.")

    state_file = Path(args.state_file) if args.state_file else None
    lease_file = Path(args.lease_file) if args.lease_file else None
    license_file = Path(args.license_file) if args.license_file else None

    prior_state = _read_json_file(state_file)
    license_payload = _read_json_file(license_file)

    install_id = args.install_id or prior_state.get("install_id")
    license_id = args.license_id or prior_state.get("license_id") or license_payload.get("license_id")
    profile = args.profile or prior_state.get("profile") or _distribution_profile(license_payload)

    tool_arguments = {
        "workspace_id": args.workspace_id,
    }
    if install_id:
        tool_arguments["install_id"] = install_id
    if args.instance_id:
        tool_arguments["instance_id"] = args.instance_id
    if args.device_id:
        tool_arguments["device_id"] = args.device_id
    if license_id:
        tool_arguments["license_id"] = license_id
    if profile:
        tool_arguments["profile"] = profile

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "review_installation",
            "arguments": tool_arguments,
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
    if not isinstance(result, dict):
        raise RuntimeError("review_installation did not return an object payload.")

    if "install_id" not in result and install_id:
        result["install_id"] = install_id
    if "license_id" not in result and license_id:
        result["license_id"] = license_id
    if "profile" not in result and profile:
        result["profile"] = profile

    activation_lease = result.get("activation_lease")
    if args.require_activation_lease and not isinstance(activation_lease, dict):
        raise RuntimeError("review_installation completed but did not return an activation lease.")

    _write_json_file(state_file, result)
    if isinstance(activation_lease, dict):
        _write_json_file(lease_file, activation_lease)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())