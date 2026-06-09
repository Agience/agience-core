import json
from pathlib import Path

import pytest

from services import types_service


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_resolve_exact_with_inheritance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Arrange: create a minimal types tree with wildcard parent and exact child.
    root = tmp_path / "types"

    _write_json(
        root / "text" / "_wildcard" / "type.json",
        {"content_type": "text/*", "version": 1},
    )
    _write_json(
        root / "text" / "_wildcard" / "preview.json",
        {"version": 1, "icon": "file-text", "preview": {"kind": "text_excerpt"}},
    )

    _write_json(
        root / "text" / "plain" / "type.json",
        {"content_type": "text/plain", "version": 1, "inherits": ["text/*"]},
    )
    _write_json(
        root / "text" / "plain" / "preview.json",
        {"version": 1, "icon": "note", "preview": {"max_chars": 12}},
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")
    monkeypatch.setattr(types_service, "_default_server_ui_roots", lambda: [])

    # Act
    res = types_service.resolve_type_definition("text/plain; charset=utf-8")

    # Assert
    assert res is not None
    assert res.content_type == "text/plain"

    preview = res.definition.get("preview")
    assert isinstance(preview, dict)

    # icon overridden by child
    assert preview.get("icon") == "note"

    # inherited kind from parent
    assert preview.get("preview", {}).get("kind") == "text_excerpt"

    # child-only field present
    assert preview.get("preview", {}).get("max_chars") == 12


def test_resolve_falls_back_to_wildcard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "types"

    _write_json(
        root / "text" / "_wildcard" / "type.json",
        {"content_type": "text/*", "version": 1},
    )
    _write_json(
        root / "text" / "_wildcard" / "preview.json",
        {"version": 1, "icon": "file-text"},
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")
    monkeypatch.setattr(types_service, "_default_server_ui_roots", lambda: [])

    res = types_service.resolve_type_definition("text/csv")
    assert res is not None
    assert res.content_type == "text/csv"
    assert res.definition.get("preview", {}).get("icon") == "file-text"


@pytest.mark.asyncio
async def test_router_resolve_uses_env_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client):
    root = tmp_path / "types"

    _write_json(
        root / "application" / "json" / "type.json",
        {"content_type": "application/json", "version": 1},
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")
    monkeypatch.setattr(types_service, "_default_server_ui_roots", lambda: [])

    resp = await client.get("/types/resolve", params={"content_type": "application/json"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_type"] == "application/json"
    assert data["definition"]["type"]["content_type"] == "application/json"
    assert data["validation_errors"] == []


def test_get_types_roots_includes_builtin_and_server_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Phase G layout: package/types/ for builtins,mantle/ chorus/<name>/ui/ for personas.
    builtin_root = tmp_path / "package" / "types"
    server_root = tmp_path / "src" / "chorus" / "astra" / "ui"

    _write_json(
        builtin_root / "application" / "json" / "type.json",
        {"content_type": "application/json", "version": 1},
    )
    _write_json(
        server_root / "application" / "vnd.agience.stream+json" / "type.json",
        {"content_type": "application/vnd.agience.stream+json", "version": 1},
    )

    monkeypatch.delenv("AGIENCE_TYPES_PATHS", raising=False)
    monkeypatch.delenv("AGIENCE_TYPES_DISABLE_BUILTIN", raising=False)
    monkeypatch.setattr(types_service, "_repo_root", lambda: tmp_path)

    roots = types_service.get_types_roots()

    assert roots == [builtin_root.resolve(), server_root.resolve()]


def test_resolve_capability_target_from_handler_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "types"

    _write_json(
        root / "application" / "vnd.test+json" / "type.json",
        {"content_type": "application/vnd.test+json", "version": 1},
    )
    _write_json(
        root / "application" / "vnd.test+json" / "handlers" / "extract_text.json",
        {"capability": "extract_text", "tool": "extract_text"},
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")

    target = types_service.resolve_capability_target("application/vnd.test+json", "extract_text")
    assert target == "extract_text"


def test_resolve_event_target_from_behaviors_handler_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "types"

    _write_json(
        root / "application" / "vnd.test+json" / "type.json",
        {"content_type": "application/vnd.test+json", "version": 1},
    )
    _write_json(
        root / "application" / "vnd.test+json" / "behaviors.json",
        {"version": 1, "events": {"on_commit": {"handler": "handlers/on_commit.json"}}},
    )
    _write_json(
        root / "application" / "vnd.test+json" / "handlers" / "on_commit.json",
        {
            "capability": "on_commit",
            "implementation": {"kind": "mcp-tool", "tool": "on_commit"},
        },
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")

    target = types_service.resolve_event_target("application/vnd.test+json", "on_commit")
    assert target == "on_commit"


def test_resolve_event_binding_prefers_event_server_over_handler_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "types"

    _write_json(
        root / "application" / "vnd.test+json" / "type.json",
        {"content_type": "application/vnd.test+json", "version": 1},
    )
    _write_json(
        root / "application" / "vnd.test+json" / "behaviors.json",
        {
            "version": 1,
            "events": {
                "on_commit": {
                    "handler": "handlers/on_commit.json",
                    "server": "event-server",
                }
            },
        },
    )
    _write_json(
        root / "application" / "vnd.test+json" / "handlers" / "on_commit.json",
        {
            "capability": "on_commit",
            "implementation": {
                "kind": "mcp-tool",
                "tool": "on_commit",
                "server": "handler-server",
            },
        },
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")

    binding = types_service.resolve_event_binding("application/vnd.test+json", "on_commit")
    assert binding == {"tool": "on_commit", "server_artifact_id": "event-server"}


def test_resolve_event_binding_supports_direct_tool_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "types"

    _write_json(
        root / "application" / "vnd.test+json" / "type.json",
        {"content_type": "application/vnd.test+json", "version": 1},
    )
    _write_json(
        root / "application" / "vnd.test+json" / "behaviors.json",
        {
            "version": 1,
            "events": {
                "on_commit": {
                    "tool": "direct_commit_tool",
                    "server_artifact_id": "direct-server",
                }
            },
        },
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")

    binding = types_service.resolve_event_binding("application/vnd.test+json", "on_commit")
    assert binding == {"tool": "direct_commit_tool", "server_artifact_id": "direct-server"}


def test_resolve_type_definition_reports_event_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "types"

    _write_json(
        root / "application" / "vnd.invalid+json" / "type.json",
        {"content_type": "application/vnd.invalid+json", "version": 1},
    )
    _write_json(
        root / "application" / "vnd.invalid+json" / "behaviors.json",
        {
            "version": 1,
            "events": {
                "on_commit": {
                    "tool": "commit_tool",
                    "handler": "handlers/on_commit.json",
                },
                "on_publish": {
                    "handler": "handlers/missing.json",
                },
            },
        },
    )
    _write_json(
        root / "application" / "vnd.invalid+json" / "handlers" / "on_commit.json",
        {
            "capability": "on_commit",
            "implementation": {"kind": "mcp-tool", "tool": "commit_tool"},
        },
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")

    res = types_service.resolve_type_definition("application/vnd.invalid+json")
    assert res is not None
    assert any("only one of 'tool' or 'handler'" in msg for msg in res.validation_errors)
    assert any("references missing handler 'missing'" in msg for msg in res.validation_errors)


def test_get_field_index_hints_extracts_per_field_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "types"

    _write_json(
        root / "application" / "vnd.example+json" / "type.json",
        {
            "content_type": "application/vnd.example+json",
            "version": 1,
            "context_schema": {
                "title": {"index": ["lexical"]},
                "description": {"index": ["lexical", "semantic"]},
                "offers": {"index": ["semantic"]},
                "location": {"index": ["geo"]},
                "price": {"index": ["numeric"]},
                "no_hints": {"type": "string"},
                "bad_hint": {"index": ["bogus"]},
                "free_form_string": "string — some prose",
            },
        },
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")
    monkeypatch.setattr(types_service, "_default_server_ui_roots", lambda: [])
    types_service.invalidate_type_cache()

    hints = types_service.get_field_index_hints("application/vnd.example+json")

    assert hints == {
        "title": ["lexical"],
        "description": ["lexical", "semantic"],
        "offers": ["semantic"],
        "location": ["geo"],
        "price": ["numeric"],
    }
    assert "no_hints" not in hints
    assert "free_form_string" not in hints
    assert "bad_hint" not in hints  # unknown hint kinds dropped silently


def test_get_field_index_hints_returns_empty_when_no_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "types"

    _write_json(
        root / "application" / "vnd.bare+json" / "type.json",
        {"content_type": "application/vnd.bare+json", "version": 1},
    )

    monkeypatch.setenv("AGIENCE_TYPES_PATHS", str(root))
    monkeypatch.setenv("AGIENCE_TYPES_DISABLE_BUILTIN", "1")
    monkeypatch.setattr(types_service, "_default_server_ui_roots", lambda: [])
    types_service.invalidate_type_cache()

    assert types_service.get_field_index_hints("application/vnd.bare+json") == {}
    assert types_service.get_field_index_hints("application/vnd.unknown+json") == {}


# ---------------------------------------------------------------------------
# Single-winner invariants — no duplicate / shadow definitions in the repo.
#
# Resolution is single-winner: `_find_type_folder` returns the first root that
# holds a content type, and `register_runtime_type` defers to any filesystem
# definition. For that to deterministically resolve to *what we expect*, a
# content type must be defined in exactly ONE place, and a `type.json` must live
# at the folder its `content_type` names. These guards fail if a shadow `type.json`
# (a persona overlay duplicating a `package/types/` canonical) is reintroduced.
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[3]
_CANONICAL_ROOT = _REPO / "package" / "types"


def _content_type_for_folder(type_json_path: Path, root: Path) -> str:
    """Inverse of `_content_type_to_rel_folder`: derive the content type a
    `type.json` is resolved under from its `<top>/<sub>` folder beneath a root
    (`_wildcard` ↦ `*`)."""
    top, sub = type_json_path.parent.relative_to(root).parts
    return f"{top}/{'*' if sub == '_wildcard' else sub}"


def _all_type_files() -> list[tuple[Path, Path]]:
    """Every checked-in `type.json` paired with the type-root it lives under
    (`package/types` + each persona's `src/chorus/<persona>/ui`)."""
    out: list[tuple[Path, Path]] = []
    roots = [_CANONICAL_ROOT, *sorted((_REPO / "src" / "chorus").glob("*/ui"))]
    for root in roots:
        for tj in sorted(root.rglob("type.json")):
            out.append((tj, root))
    return out


def test_no_duplicate_type_definitions_across_roots():
    """Each content type is defined in exactly one folder across all type roots —
    no canonical/persona shadow pairs. This is what makes single-winner resolution
    unambiguous: there is only ever one definition to win."""
    locations: dict[str, list[str]] = {}
    for tj, root in _all_type_files():
        ct = _content_type_for_folder(tj, root)
        locations.setdefault(ct, []).append(tj.relative_to(_REPO).as_posix())

    dups = {ct: locs for ct, locs in locations.items() if len(locs) > 1}
    assert not dups, "content type(s) defined in more than one folder (shadow/duplicate):\n" + "\n".join(
        f"  {ct}:\n" + "\n".join(f"      {p}" for p in locs) for ct, locs in sorted(dups.items())
    )


def test_declared_content_type_matches_folder_location():
    """A `type.json`'s declared `content_type` must equal the type its folder
    resolves under — otherwise the resolver finds it by one name but the loaded
    definition claims another."""
    mismatches = []
    for tj, root in _all_type_files():
        declared = json.loads(tj.read_text(encoding="utf-8-sig")).get("content_type")
        expected = _content_type_for_folder(tj, root)
        if declared != expected:
            mismatches.append(f"  {tj.relative_to(_REPO).as_posix()}: declares {declared!r}, folder says {expected!r}")
    assert not mismatches, "content_type does not match folder location:\n" + "\n".join(mismatches)


@pytest.mark.parametrize(
    "content_type",
    [
        "application/vnd.agience.authority+json",
        "application/vnd.agience.resource+json",
        "application/vnd.agience.prompt+json",
        "application/vnd.agience.collection+json",
        "application/vnd.agience.workspace+json",
    ],
)
def test_known_types_resolve_to_canonical(content_type, monkeypatch: pytest.MonkeyPatch):
    """The formerly-shadowed (and other core) types resolve to the `package/types`
    canonical definition — single winner resolving to exactly what we expect."""
    monkeypatch.delenv("AGIENCE_TYPES_PATHS", raising=False)
    monkeypatch.delenv("AGIENCE_TYPES_DISABLE_BUILTIN", raising=False)
    types_service.invalidate_type_cache()

    res = types_service.resolve_type_definition(content_type)
    assert res is not None, f"{content_type} did not resolve"
    # The type's own folder is always the last entry in `sources` (parents prepend).
    own_folder = Path(res.sources[-1]).resolve()
    assert _CANONICAL_ROOT.resolve() in own_folder.parents, (
        f"{content_type} resolved to {own_folder} — expected a definition under package/types"
    )


def test_no_type_json_carries_a_utf8_bom():
    """Keep every committed type.json BOM-free. MANTLE reads `utf-8-sig` and
    FACET's build now strips a BOM too, but a stray BOM is a latent trap — it
    parses server-side yet (historically) silently dropped the type on the
    frontend. Guard the files so neither resolver has to compensate."""
    bom = b"\xef\xbb\xbf"
    offenders = [
        tj.relative_to(_REPO).as_posix()
        for tj, _root in _all_type_files()
        if tj.read_bytes().startswith(bom)
    ]
    assert not offenders, "type.json file(s) start with a UTF-8 BOM:\n" + "\n".join(
        f"  {p}" for p in offenders
    )
