"""manage_addons — add-on manifest registration helpers (${VAR} substitution +
card discovery). The DB-applying `register` path is covered by the seed loader
tests; here we test the pure pre-apply helpers."""

import manage_addons as ma


def test_collect_vars_parses_pairs():
    assert ma._collect_vars(["A=1", "B=two"]) == {"A": "1", "B": "two"}


def test_substitute_tree_replaces_tokens_and_flags_unresolved(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.yaml").write_text("url: ${BEACON_PUBLIC_URL}\nname: x\n", encoding="utf-8")
    (src / "b.yaml").write_text("missing: ${NOT_SET}\n", encoding="utf-8")
    dst = tmp_path / "dst"

    unresolved = ma._substitute_tree(src, dst, {"BEACON_PUBLIC_URL": "https://beacon.agience.ai"})

    assert "https://beacon.agience.ai" in (dst / "a.yaml").read_text(encoding="utf-8")
    assert unresolved == ["NOT_SET"]


def test_list_cards_finds_slugged_yaml(tmp_path):
    (tmp_path / "server.yaml").write_text(
        "slug: agience-server-beacon\ncontent_type: application/vnd.agience.mcp-server+json\n",
        encoding="utf-8",
    )
    (tmp_path / "notacard.yaml").write_text("just: data\n", encoding="utf-8")  # no slug → skipped

    cards = ma._list_cards(tmp_path)

    assert cards == [("application/vnd.agience.mcp-server+json", "agience-server-beacon")]
