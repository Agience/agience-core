#!/usr/bin/env python3
"""manage_addons.py — register an external add-on's artifact manifest.

An *add-on* is a service external to agience-core (e.g. the closed Beacon
premium service) that contributes artifacts/edges/grants to the platform DB. Its
manifest is a directory of seed-format cards — the SAME declarative format as
`package/seeds/` — so it is applied through the canonical loader
`seed_provisioning.seed_from_artifacts`. That loader is what makes registration
correct: besides creating the artifacts and edges, it calls
`platform_topology.register_id(slug, uuid)`, so a `namespace/slug` reference
(e.g. a search flavor's `run.server: agience/agience-server-beacon`) resolves at
dispatch time. A plain `POST /artifacts` would NOT register the slug.

This tool is generic — it knows nothing about any specific add-on. Point it at a
manifest's `artifacts/` directory and pass any `${VAR}` substitutions the
manifest declares (e.g. the add-on's public URL).

Per-user grants in a manifest (templated with `{{user.id}}`) are NOT applied
here — those are provisioned per entitled user by the economics service (Ophan)
when the entitlement is granted. Point this tool at the platform `artifacts/`
directory only.

Usage
-----
  python manage_addons.py register --manifest /path/to/addon/manifest/artifacts \
      --set BEACON_PUBLIC_URL=https://beacon.internal:8090
  python manage_addons.py register --manifest ... --set KEY=VAL --dry-run
"""

import argparse
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s  %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("manage_addons")

_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _collect_vars(pairs: list[str]) -> dict[str, str]:
    """Merge --set KEY=VAL pairs over the process environment."""
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--set expects KEY=VALUE, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = v
    return out


def _substitute_tree(src: Path, dst: Path, variables: dict[str, str]) -> list[str]:
    """Copy ``src`` → ``dst`` substituting ``${VAR}`` tokens. Returns unresolved tokens."""
    unresolved: set[str] = set()

    def _sub(text: str) -> str:
        def repl(m: "re.Match[str]") -> str:
            key = m.group(1)
            val = variables.get(key, os.environ.get(key))
            if val is None:
                unresolved.add(key)
                return m.group(0)
            return val
        return _VAR_RE.sub(repl, text)

    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in {".yaml", ".yml", ".json"}:
            target.write_text(_sub(path.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            shutil.copy2(path, target)
    return sorted(unresolved)


def _list_cards(root: Path) -> list[tuple[str, str]]:
    """Best-effort (content_type, slug) list of artifact cards under ``root``."""
    import yaml

    cards: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.yaml")):
        try:
            body = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(body, dict) and body.get("slug"):
            cards.append((body.get("content_type") or body.get("type") or "?", body["slug"]))
    return cards


def action_register(manifest: str, sets: list[str], dry_run: bool) -> None:
    src = Path(manifest)
    if not src.is_dir():
        raise SystemExit(f"--manifest must be a directory: {manifest}")

    variables = _collect_vars(sets)
    with tempfile.TemporaryDirectory(prefix="addon-manifest-") as tmp:
        tmp_root = Path(tmp)
        unresolved = _substitute_tree(src, tmp_root, variables)
        if unresolved:
            logger.warning("Unresolved ${...} tokens (pass via --set): %s", ", ".join(unresolved))

        cards = _list_cards(tmp_root)
        logger.info("Manifest %s — %d artifact card(s):", manifest, len(cards))
        for ct, slug in cards:
            logger.info("  - %s  (%s)", slug, ct)

        if dry_run:
            logger.info("[DRY-RUN] Not applying. Re-run without --dry-run to register.")
            if unresolved:
                raise SystemExit("Refusing to suggest apply: unresolved tokens remain.")
            return

        if unresolved:
            raise SystemExit("Refusing to apply with unresolved ${...} tokens.")

        from schemas.arango.loader import init_arango_db
        from services.seed_provisioning import seed_from_artifacts

        db = init_arango_db()
        report = seed_from_artifacts(db, tmp_root, user=None)
        logger.info("Registered: %s", report.summary())
        for err in report.errors:
            logger.error("  seed error: %s", err)
        if report.errors:
            raise SystemExit(f"Registration completed with {len(report.errors)} error(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Register an external add-on artifact manifest.")
    sub = parser.add_subparsers(dest="action", required=True)
    reg = sub.add_parser("register", help="Apply an add-on manifest's artifacts/ directory.")
    reg.add_argument("--manifest", required=True, help="Path to the manifest artifacts directory.")
    reg.add_argument("--set", action="append", default=[], help="Substitution KEY=VALUE (repeatable).")
    reg.add_argument("--dry-run", action="store_true", help="Substitute + list cards, do not apply.")
    args = parser.parse_args()
    if args.action == "register":
        action_register(args.manifest, args.set, args.dry_run)


if __name__ == "__main__":
    main()
