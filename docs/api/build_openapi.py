#!/usr/bin/env python
"""Consolidate the core-platform REST surface into a single OpenAPI 3.1 document.

Covers the static, code-defined HTTP services only — Origin (identity/OIDC) and
Mantle (artifacts/search/secrets/stream/events/types). Dynamic surfaces (Chorus
persona MCP tools, Beacon) are intentionally excluded.

The two FastAPI apps have different sys.path conventions and bare-import roots,
so each spec is dumped in its own subprocess (clean interpreter) and merged here.
No database or running service is required — `app.openapi()` only introspects
routes, and both apps defer all DB work to their lifespan handlers.

Usage:
    python docs/api/build_openapi.py            # write docs/api/openapi.json
    python docs/api/build_openapi.py --check     # fail if the committed file is stale
    python docs/api/build_openapi.py --dump <service> <outfile>   # internal
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
OUT = REPO_ROOT / "docs" / "api" / "openapi.json"

# --- Routing config -------------------------------------------------------
# Subdomain-per-service. Each service answers at <host>.<install> (e.g.
# mantle.agience.ai). The install root is a server VARIABLE so the same file
# serves the SaaS (agience.ai), a dedicated install (foresight.on.agience.ai),
# and self-host (xyz.com) — the consumer just changes `install`. Paths stay at
# the service root (no `/api` prefix); each operation carries its own server.
SERVICES = {
    "origin": {"module": "origin.main", "host": "origin", "group": "Origin (identity / OIDC / grants)"},
    "mantle": {"module": "mantle.main", "host": "mantle", "group": "Mantle (artifacts / search / stream)"},
}

INSTALL_DEFAULT = "agience.ai"
# Operational endpoints that every service exposes and that would collide once
# the `/api`-style prefix is gone. They aren't useful API surface — drop them.
HOUSEKEEPING = {"/", "/status", "/version", "/healthz"}


def _server_for(host: str) -> dict:
    return {
        "url": f"https://{host}.{{install}}",
        "variables": {
            "install": {
                "default": INSTALL_DEFAULT,
                "description": "Install root domain — agience.ai (SaaS), a dedicated install "
                "(e.g. foresight.on.agience.ai), or your self-hosted domain.",
            }
        },
    }

TITLE = "Agience Platform API"
DESCRIPTION = (
    "Consolidated REST surface for the Agience core platform: Origin (identity, "
    "OIDC, grants, keys) and Mantle (artifacts, search, secrets, stream, events, "
    "types). MCP tool surfaces (Chorus personas, Beacon) are documented separately."
)


def _version() -> str:
    try:
        return json.loads((REPO_ROOT / "build_info.json").read_text()).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def dump_one(service: str, outfile: str) -> None:
    """Subprocess entrypoint: import a service's app and write its raw spec."""
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    module = SERVICES[service]["module"]
    mod = __import__(module, fromlist=["app"])
    Path(outfile).write_text(json.dumps(mod.app.openapi()), encoding="utf-8")


def _harvest(service: str, tmp: Path) -> dict:
    out = tmp / f"{service}.json"
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--dump", service, str(out)],
        check=True,
        cwd=str(REPO_ROOT),
    )
    return json.loads(out.read_text(encoding="utf-8"))


def _rewrite_refs(node, rename: dict[str, str]):
    """Recursively rewrite #/components/schemas/<old> refs to <new>."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            if name in rename:
                node["$ref"] = f"#/components/schemas/{rename[name]}"
        for v in node.values():
            _rewrite_refs(v, rename)
    elif isinstance(node, list):
        for v in node:
            _rewrite_refs(v, rename)


def merge() -> dict:
    import tempfile

    merged_paths: dict = {}
    merged_schemas: dict = {}
    tag_groups: list[dict] = []
    seen_security: dict = {}
    top_servers: list[dict] = []

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for service, cfg in SERVICES.items():
            spec = _harvest(service, tmp)
            server = _server_for(cfg["host"])
            top_servers.append(server)
            schemas = spec.get("components", {}).get("schemas", {})

            # Resolve schema-name collisions: dedupe identical, namespace differing.
            rename: dict[str, str] = {}
            for name, schema in schemas.items():
                if name in merged_schemas:
                    if merged_schemas[name] == schema:
                        continue  # identical (e.g. FastAPI's HTTPValidationError)
                    rename[name] = f"{service.capitalize()}_{name}"
            local_schemas = copy.deepcopy(schemas)
            local_paths = copy.deepcopy(spec.get("paths", {}))
            if rename:
                _rewrite_refs(local_schemas, rename)
                _rewrite_refs(local_paths, rename)
                for old, new in rename.items():
                    local_schemas[new] = local_schemas.pop(old)

            merged_schemas.update(local_schemas)
            seen_security.update(spec.get("components", {}).get("securitySchemes", {}))

            service_tags: list[str] = []
            for path, item in local_paths.items():
                if path in HOUSEKEEPING:
                    continue
                # Each service answers on its own host — pin the server per path
                # so try-it hits the right subdomain regardless of install root.
                item["servers"] = [server]
                merged_paths[path] = item
                for method, op in item.items():
                    if not isinstance(op, dict):
                        continue
                    for t in op.get("tags", []):
                        if t not in service_tags:
                            service_tags.append(t)
            tag_groups.append({"name": cfg["group"], "tags": service_tags})

    doc = {
        "openapi": "3.1.0",
        "info": {"title": TITLE, "version": _version(), "description": DESCRIPTION},
        "servers": top_servers,
        "paths": dict(sorted(merged_paths.items())),
        "components": {"schemas": dict(sorted(merged_schemas.items()))},
        "x-tagGroups": tag_groups,
    }
    if seen_security:
        doc["components"]["securitySchemes"] = seen_security
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", nargs=2, metavar=("SERVICE", "OUTFILE"))
    ap.add_argument("--check", action="store_true", help="fail if committed file is stale")
    args = ap.parse_args()

    if args.dump:
        dump_one(args.dump[0], args.dump[1])
        return 0

    doc = merge()
    rendered = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != rendered:
            print("openapi.json is stale — run: python docs/api/build_openapi.py", file=sys.stderr)
            return 1
        print("openapi.json is up to date.")
        return 0

    OUT.write_text(rendered, encoding="utf-8")
    n_ops = sum(1 for item in doc["paths"].values() for m in item if isinstance(item[m], dict))
    print(f"Wrote {OUT.relative_to(REPO_ROOT)} — {len(doc['paths'])} paths, {n_ops} operations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
