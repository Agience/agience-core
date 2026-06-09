"""Drift guards: the static platform seed files must stay in lock-step with the
manifest-/code-derived sources of truth. Adding a persona, server, or default
LLM connection without its seed file (or vice-versa) fails CI here — converting
the "two-place edit" risk of static seeds into an enforced invariant.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from services import server_registry
from services.bootstrap_types import (
    AGENT_CONTENT_TYPE,
    ALL_PLATFORM_COLLECTION_SLUGS,
    LLM_CONNECTION_CONTENT_TYPE,
    MCP_SERVER_CONTENT_TYPE,
    PLATFORM_AGENT_SLUGS,
    PLATFORM_LLM_CONNECTION_SLUGS,
)

_COLLECTION_CONTENT_TYPE = "application/vnd.agience.collection+json"

# Flat trigger/kind layout: seeds/<platform|admin|user>/<artifacts|grants>/.
# The categorical subfolders (agents/, servers/, llm/) are gone — a seed's
# category is read from its `content_type`, not its directory, because
# containment is expressed by each artifact's `contained_by` slug reference.
_REPO = Path(__file__).resolve().parents[3]
_PLATFORM_ARTIFACTS = _REPO / "package" / "seeds" / "platform" / "artifacts"
_USER_GRANTS = _REPO / "package" / "seeds" / "user" / "grants"
_ADMIN_GRANTS = _REPO / "package" / "seeds" / "admin" / "grants"


def _platform_bodies() -> list[dict]:
    return [
        body
        for p in sorted(_PLATFORM_ARTIFACTS.glob("*.yaml"))
        if isinstance(body := yaml.safe_load(p.read_text(encoding="utf-8")), dict)
    ]


def _load(content_type: str) -> list[dict]:
    """Platform artifact seeds of a given content type (folder-independent)."""
    return [b for b in _platform_bodies() if b.get("content_type") == content_type]


def _grant_resources(grant_dir: Path) -> set[str]:
    """Collect every resource slug a grant set targets (handles `resource` and
    `resources:` list; strips the namespace prefix)."""
    out: set[str] = set()
    for p in sorted(grant_dir.glob("*.yaml")):
        body = yaml.safe_load(p.read_text(encoding="utf-8"))
        res = body.get("resources") or ([body["resource"]] if body.get("resource") else [])
        for r in res:
            out.add(r.split("/", 1)[1] if "/" in r else r)
    return out


def test_server_seed_files_match_manifest():
    bodies = _load(MCP_SERVER_CONTENT_TYPE)
    by_slug = {b["slug"]: b for b in bodies}
    expected = {f"agience-server-{e.name}" for e in server_registry.all_entries()} | {"agience-core"}
    assert set(by_slug) == expected, "server seed files drifted from chorus/manifest.json"

    # Per-persona fields must mirror the manifest entry exactly.
    for entry in server_registry.all_entries():
        ctx = by_slug[f"agience-server-{entry.name}"]["context"]["mcp_server"]
        assert ctx["name"] == entry.name
        assert ctx["role"] == entry.role
        assert ctx["client_id"] == entry.client_id
        assert ctx["transport"] == "builtin"


def test_agent_seed_files_match_persona_list():
    slugs = {b["slug"] for b in _load(AGENT_CONTENT_TYPE)}
    assert slugs == {f"agience-agent-{s}" for s in PLATFORM_AGENT_SLUGS}


def test_llm_seed_files_match_connection_list():
    slugs = {b["slug"] for b in _load(LLM_CONNECTION_CONTENT_TYPE)}
    assert slugs == {f"agience-llm-{s}" for s in PLATFORM_LLM_CONNECTION_SLUGS}


def test_platform_collection_slugs_match_seeds():
    """Every slug in ALL_PLATFORM_COLLECTION_SLUGS has a collection seed file, and
    no collection seed exists outside that canonical list. Catches a vestigial
    slug (listed but never created — e.g. the old operator collection) and an
    unlisted collection (seeded but not in the canonical set)."""
    seeded = {
        b.get("slug")
        for b in _platform_bodies()
        if b.get("content_type") == _COLLECTION_CONTENT_TYPE
    }
    assert seeded == set(ALL_PLATFORM_COLLECTION_SLUGS)


def test_user_grants_cover_every_platform_collection():
    """Every platform collection receives a first-login user grant, and none
    targets a collection outside the canonical platform set."""
    assert _grant_resources(_USER_GRANTS) == set(ALL_PLATFORM_COLLECTION_SLUGS)


def test_admin_grants_cover_every_platform_collection():
    """The designated platform admin's grant set covers exactly the platform
    collections (full management access), nothing more or less."""
    assert _grant_resources(_ADMIN_GRANTS) == set(ALL_PLATFORM_COLLECTION_SLUGS)
