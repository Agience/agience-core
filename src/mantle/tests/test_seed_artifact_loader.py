"""Tests for the declarative-bootstrap artifact loader.

The loader replaces imperative `services/seed_provisioning/*.py` modules
with artifacts under `package/seeds/<namespace>/`. These tests cover the
deterministic-UUID derivation, template + reference resolution, and
idempotent upsert path against a mocked Arango database.

See `.dev/features/declarative-bootstrap-artifacts.md` for the full design.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.seed_provisioning import loader


@pytest.fixture(autouse=True)
def _clear_topology_registry():
    """Isolate the module-global platform_topology registry between tests — the
    loader now reads it first (get_id_optional), so a leaked id would bleed
    across tests that each use a distinct instance namespace. Also stub id
    persistence (the MagicMock DB can't run platform_settings.set_many)."""
    from services import platform_topology

    platform_topology.clear_registry()
    with patch("services.seed_provisioning.loader._persist_seed_ids"):
        yield
    platform_topology.clear_registry()


# ---------------------------------------------------------------------------
# Instance namespace
# ---------------------------------------------------------------------------


def test_get_instance_namespace_writes_and_returns_uuid(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))
    ns_a = loader.get_instance_namespace()
    assert isinstance(ns_a, uuid.UUID)
    assert (tmp_path / "instance.uuid").is_file()
    # Calling twice must return the same UUID (idempotent).
    ns_b = loader.get_instance_namespace()
    assert ns_a == ns_b


def test_get_instance_namespace_rotates_when_unreadable(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))
    (tmp_path / "instance.uuid").write_text("not-a-uuid", encoding="utf-8")
    ns = loader.get_instance_namespace()
    assert isinstance(ns, uuid.UUID)
    assert (tmp_path / "instance.uuid").read_text(encoding="utf-8").strip() == str(ns)


def test_derive_uuid_is_deterministic():
    ns = uuid.UUID("11111111-1111-1111-1111-111111111111")
    a = loader.derive_uuid(ns, "agience", "authority")
    b = loader.derive_uuid(ns, "agience", "authority")
    c = loader.derive_uuid(ns, "agience", "host")
    d = loader.derive_uuid(uuid.UUID("22222222-2222-2222-2222-222222222222"), "agience", "authority")
    assert a == b
    assert a != c          # different slug → different UUID
    assert a != d          # different instance namespace → different UUID


# ---------------------------------------------------------------------------
# Templating + ref resolution
# ---------------------------------------------------------------------------


def test_walk_resolve_substitutes_config_directive(monkeypatch):
    from kernel import config
    monkeypatch.setattr(config, "AUTHORITY_ISSUER", "http://test.example/")
    out = loader._walk_resolve(
        {"issuer": "{{config.AUTHORITY_ISSUER}}"},
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        refs={},
    )
    assert out == {"issuer": "http://test.example/"}


def test_walk_resolve_leaves_partial_template_alone():
    out = loader._walk_resolve(
        {"label": "prefix-{{config.AUTHORITY_ISSUER}}"},
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        refs={},
    )
    assert out == {"label": "prefix-{{config.AUTHORITY_ISSUER}}"}


def test_walk_resolve_substitutes_refs():
    refs = {"agience/authority": "00000000-0000-0000-0000-000000000abc"}
    out = loader._walk_resolve(
        {"target": "agience/authority", "literal": "not-a-ref"},
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        refs=refs,
    )
    assert out == {
        "target": "00000000-0000-0000-0000-000000000abc",
        "literal": "not-a-ref",
    }


def test_walk_resolve_file_directive_with_key(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))
    manifest = {"trust_anchors": {"chorus": {"jwks": {"keys": []}}}, "issuer": "x"}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = loader._walk_resolve(
        {"anchors": "{{file:manifest.json:trust_anchors}}"},
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        refs={},
    )
    assert out == {"anchors": {"chorus": {"jwks": {"keys": []}}}}


def test_walk_resolve_file_directive_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path))
    out = loader._walk_resolve(
        {"x": "{{file:missing.json:key}}"},
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        refs={},
    )
    assert out == {"x": None}


# ---------------------------------------------------------------------------
# Artifact discovery
# ---------------------------------------------------------------------------


def test_discover_cards_finds_yaml_and_json(tmp_path):
    (tmp_path / "agience").mkdir()
    (tmp_path / "agience" / "a.yaml").write_text(
        "namespace: agience\nslug: a\ncontent_type: application/vnd.agience.collection+json\n",
        encoding="utf-8",
    )
    (tmp_path / "agience" / "b.json").write_text(
        json.dumps({"namespace": "agience", "slug": "b", "content_type": "application/json"}),
        encoding="utf-8",
    )
    (tmp_path / "agience" / "_skip.yaml").write_text("namespace: x\nslug: skip\n", encoding="utf-8")
    (tmp_path / "agience" / "not-a-artifact.txt").write_text("ignore me", encoding="utf-8")
    artifacts = loader._discover_cards(tmp_path)
    slugs = {c.body["slug"] for c in artifacts}
    assert slugs == {"a", "b"}


def test_discover_cards_skips_non_dict_root(tmp_path):
    (tmp_path / "list.yaml").write_text("- 1\n- 2\n", encoding="utf-8")
    (tmp_path / "ok.yaml").write_text("namespace: agience\nslug: ok\n", encoding="utf-8")
    artifacts = loader._discover_cards(tmp_path)
    assert {c.body["slug"] for c in artifacts} == {"ok"}


def test_discover_cards_returns_empty_when_root_missing(tmp_path):
    artifacts = loader._discover_cards(tmp_path / "nope")
    assert artifacts == []


# ---------------------------------------------------------------------------
# End-to-end: seed_from_artifacts
# ---------------------------------------------------------------------------


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def seeds_root(tmp_path) -> Path:
    root = tmp_path / "seeds"
    _write(
        root / "agience" / "auth-coll.yaml",
        "namespace: agience\n"
        "slug: authority-collection\n"
        "content_type: application/vnd.agience.collection+json\n"
        "name: Auth\n",
    )
    _write(
        root / "agience" / "auth.yaml",
        "namespace: agience\n"
        "slug: authority\n"
        "content_type: application/vnd.agience.authority+json\n"
        "name: Authority\n"
        "context:\n  hi: there\n"
        "content: ''\n"
        "edges:\n"
        "  - rel: contained_by\n"
        "    to: agience/authority-collection\n"
        "    origin: true\n"
        "    order_key: a0\n",
    )
    return root


def test_seed_from_artifacts_inserts_collection_then_artifact_then_edge(seeds_root, tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    db = MagicMock()
    with (
        patch("services.seed_provisioning.loader.db_get_collection_by_id", return_value=None),
        patch("services.seed_provisioning.loader.db_create_collection") as mock_create_coll,
        patch("services.seed_provisioning.loader.db_get_artifact", return_value=None),
        patch("services.seed_provisioning.loader.db_create_artifact") as mock_create_art,
        patch("services.seed_provisioning.loader.db_get_edge", return_value=None),
        patch("services.seed_provisioning.loader.db_add_artifact_to_collection") as mock_add_to_coll,
    ):
        report = loader.seed_from_artifacts(db, seeds_root)

    assert report.artifacts_added == 2
    assert report.artifacts_skipped == 0
    assert report.edges_added == 1
    assert report.errors == []

    # Collection created with deterministic UUID derived from the instance namespace.
    inst_ns = loader.get_instance_namespace()
    coll_uuid = loader.derive_uuid(inst_ns, "agience", "authority-collection")
    art_uuid = loader.derive_uuid(inst_ns, "agience", "authority")
    created_coll = mock_create_coll.call_args.args[1]
    assert created_coll.id == coll_uuid
    created_art = mock_create_art.call_args.args[1]
    assert created_art.id == art_uuid
    # Containment backfills collection_id from the origin edge.
    assert created_art.collection_id == coll_uuid

    # Containment edge: container(_from)=collection, child(_to)=artifact root,
    # order_key from YAML, origin edge, no relationship label.
    args = mock_add_to_coll.call_args.args
    kwargs = mock_add_to_coll.call_args.kwargs
    assert args[1] == coll_uuid       # container
    assert args[2] == art_uuid        # child
    assert args[3] == "a0"            # order_key (was buggily the uuid before)
    assert kwargs["origin"] is True
    assert kwargs["relationship"] is None
    assert kwargs["propagate"] is None


def test_seed_from_artifacts_is_idempotent_on_existing_artifacts(seeds_root, tmp_path, monkeypatch):
    """Re-running with the same artifacts already in the DB skips, doesn't error."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    db = MagicMock()
    with (
        patch("services.seed_provisioning.loader.db_get_collection_by_id", return_value=MagicMock()),
        patch("services.seed_provisioning.loader.db_create_collection") as mock_create_coll,
        patch("services.seed_provisioning.loader.db_get_artifact", return_value=MagicMock()),
        patch("services.seed_provisioning.loader.db_create_artifact") as mock_create_art,
        patch("services.seed_provisioning.loader.db_add_artifact_to_collection"),
    ):
        report = loader.seed_from_artifacts(db, seeds_root)

    mock_create_coll.assert_not_called()
    mock_create_art.assert_not_called()
    assert report.artifacts_added == 0
    assert report.artifacts_skipped == 2
    assert report.errors == []


def test_seed_from_artifacts_returns_empty_report_when_no_cards(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    db = MagicMock()
    report = loader.seed_from_artifacts(db, tmp_path / "nope")
    assert report.artifacts_added == 0
    assert report.errors == []


def test_seed_from_artifacts_applies_typed_edge(tmp_path, monkeypatch):
    """A non-containment edge becomes a relationship-labelled edge from this
    artifact to its target (origin defaults false, no grant propagation)."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    root = tmp_path / "seeds"
    _write(
        root / "agience" / "a.yaml",
        "namespace: agience\nslug: a\n"
        "content_type: application/vnd.agience.collection+json\n",
    )
    _write(
        root / "agience" / "b.yaml",
        "namespace: agience\nslug: b\n"
        "content_type: application/vnd.agience.thing+json\n"
        "edges:\n"
        "  - rel: operator\n    to: agience/a\n",
    )
    db = MagicMock()
    with (
        patch("services.seed_provisioning.loader.db_get_collection_by_id", return_value=None),
        patch("services.seed_provisioning.loader.db_create_collection"),
        patch("services.seed_provisioning.loader.db_get_artifact", return_value=None),
        patch("services.seed_provisioning.loader.db_create_artifact"),
        patch("services.seed_provisioning.loader.db_get_edge", return_value=None),
        patch("services.seed_provisioning.loader.db_add_artifact_to_collection") as mock_add,
    ):
        report = loader.seed_from_artifacts(db, root)

    assert report.errors == []
    assert report.edges_added == 1
    inst_ns = loader.get_instance_namespace()
    a_uuid = loader.derive_uuid(inst_ns, "agience", "a")
    b_uuid = loader.derive_uuid(inst_ns, "agience", "b")
    args, kwargs = mock_add.call_args.args, mock_add.call_args.kwargs
    assert args[1] == b_uuid              # typed edge originates from this artifact
    assert args[2] == a_uuid              # → target
    assert kwargs["relationship"] == "operator"
    assert kwargs["origin"] is False


def test_seed_from_artifacts_edge_idempotent_skips_existing(seeds_root, tmp_path, monkeypatch):
    """An existing edge is never overwritten (preserves order_key on re-seed)."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    db = MagicMock()
    with (
        patch("services.seed_provisioning.loader.db_get_collection_by_id", return_value=None),
        patch("services.seed_provisioning.loader.db_create_collection"),
        patch("services.seed_provisioning.loader.db_get_artifact", return_value=None),
        patch("services.seed_provisioning.loader.db_create_artifact"),
        patch("services.seed_provisioning.loader.db_get_edge", return_value={"_key": "exists"}),
        patch("services.seed_provisioning.loader.db_add_artifact_to_collection") as mock_add,
    ):
        report = loader.seed_from_artifacts(db, seeds_root)

    mock_add.assert_not_called()
    assert report.edges_added == 0
    assert report.edges_skipped == 1


def test_seed_from_artifacts_applies_grant(tmp_path, monkeypatch):
    """A grant artifact upserts a user→resource grant with the right CRUDEASIO flags."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    root = tmp_path / "seeds"
    _write(
        root / "agience" / "grants" / "g1.yaml",
        "type: grant\nnamespace: agience\nslug: g1\n"
        "principal: 11111111-1111-1111-1111-111111111111\n"
        "resource: 22222222-2222-2222-2222-222222222222\n"
        "actions: [read, invoke]\n",
    )
    db = MagicMock()
    with patch(
        "services.seed_provisioning.loader.db_upsert_user_collection_grant",
        return_value=(MagicMock(), True),
    ) as mock_grant:
        report = loader.seed_from_artifacts(db, root)

    assert report.errors == []
    assert report.grants_added == 1
    kwargs = mock_grant.call_args.kwargs
    assert kwargs["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert kwargs["collection_id"] == "22222222-2222-2222-2222-222222222222"
    assert kwargs["can_read"] is True
    assert kwargs["can_invoke"] is True
    assert kwargs["can_update"] is False


def test_seed_from_artifacts_grant_resolves_user_principal(tmp_path, monkeypatch):
    """`principal: {{user.id}}` resolves from the user context."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    root = tmp_path / "seeds"
    _write(
        root / "agience" / "grants" / "g.yaml",
        "type: grant\nnamespace: agience\nslug: g\n"
        'principal: "{{user.id}}"\n'
        "resource: 22222222-2222-2222-2222-222222222222\n"
        "actions: [read]\n",
    )
    db = MagicMock()
    user = loader.UserContext(id="user-abc")
    with patch(
        "services.seed_provisioning.loader.db_upsert_user_collection_grant",
        return_value=(MagicMock(), True),
    ) as mock_grant:
        report = loader.seed_from_artifacts(db, root, user=user)

    assert report.errors == []
    assert mock_grant.call_args.kwargs["user_id"] == "user-abc"


def test_seed_from_artifacts_grant_resources_list(tmp_path, monkeypatch):
    """A grant with `resources: [...]` upserts one grant per resource."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    root = tmp_path / "seeds"
    _write(
        root / "agience" / "grants" / "g.yaml",
        "type: grant\nnamespace: agience\nslug: g\n"
        'principal: "{{user.id}}"\n'
        "actions: [read, admin]\n"
        "resources:\n"
        "  - 11111111-1111-1111-1111-111111111111\n"
        "  - 22222222-2222-2222-2222-222222222222\n",
    )
    db = MagicMock()
    with patch(
        "services.seed_provisioning.loader.db_upsert_user_collection_grant",
        side_effect=lambda db, **kw: (MagicMock(), True),
    ) as mock_grant:
        report = loader.seed_from_artifacts(db, root, user=loader.UserContext(id="u1"))
    assert report.errors == []
    assert report.grants_added == 2
    cols = {c.kwargs["collection_id"] for c in mock_grant.call_args_list}
    assert cols == {
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    }
    for c in mock_grant.call_args_list:
        assert c.kwargs["user_id"] == "u1"
        assert c.kwargs["can_read"] and c.kwargs["can_admin"]


def test_seed_from_artifacts_grants_union_by_principal_resource(tmp_path, monkeypatch):
    """Two grant cards on the same (principal, resource) union their actions —
    one write with the combined flags, order-independent."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    root = tmp_path / "seeds"
    res = "22222222-2222-2222-2222-222222222222"
    _write(root / "agience" / "grants" / "a-read.yaml",
           f"type: grant\nnamespace: agience\nslug: a\nprincipal: u1\nresource: {res}\nactions: [read]\n")
    _write(root / "agience" / "grants" / "b-admin.yaml",
           f"type: grant\nnamespace: agience\nslug: b\nprincipal: u1\nresource: {res}\nactions: [admin]\n")
    db = MagicMock()
    with patch(
        "services.seed_provisioning.loader.db_upsert_user_collection_grant",
        side_effect=lambda db, **kw: (MagicMock(), True),
    ) as mock_grant:
        report = loader.seed_from_artifacts(db, root)
    assert report.errors == []
    assert mock_grant.call_count == 1  # one unioned write
    kw = mock_grant.call_args.kwargs
    assert kw["can_read"] and kw["can_admin"]


def test_seed_from_artifacts_grant_unresolved_principal_errors(tmp_path, monkeypatch):
    """A principal ref that resolves to nothing surfaces an error, not a bad grant."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    root = tmp_path / "seeds"
    _write(
        root / "agience" / "grants" / "g.yaml",
        "type: grant\nnamespace: agience\nslug: g\n"
        "principal: agience/nonexistent\n"
        "resource: 22222222-2222-2222-2222-222222222222\n"
        "actions: [read]\n",
    )
    db = MagicMock()
    with patch("services.seed_provisioning.loader.db_upsert_user_collection_grant") as mock_grant:
        report = loader.seed_from_artifacts(db, root)
    mock_grant.assert_not_called()
    assert any("unresolved grant principal" in e for e in report.errors)


def test_walk_resolve_user_directive():
    user = loader.UserContext(id="uid-1", email="u@example.com")
    out = loader._walk_resolve(
        {"who": "{{user.id}}", "mail": "{{user.email}}", "missing": "{{user.nope}}"},
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        refs={},
        user=user,
    )
    assert out == {"who": "uid-1", "mail": "u@example.com", "missing": None}


def test_walk_resolve_ref_falls_back_to_topology(monkeypatch):
    """A ref absent from the local table resolves via the platform topology
    registry (cross-run: per-user seeds referencing platform artifacts)."""
    from services import platform_topology

    platform_topology.register_id("agience-authorities", "topo-uuid-123")
    out = loader._walk_resolve(
        {"resource": "agience/agience-authorities"},
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        refs={},
    )
    assert out == {"resource": "topo-uuid-123"}


def test_seed_from_artifacts_registers_slug_in_platform_topology(seeds_root, tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    db = MagicMock()
    with (
        patch("services.seed_provisioning.loader.db_get_collection_by_id", return_value=None),
        patch("services.seed_provisioning.loader.db_create_collection"),
        patch("services.seed_provisioning.loader.db_get_artifact", return_value=None),
        patch("services.seed_provisioning.loader.db_create_artifact"),
        patch("services.seed_provisioning.loader.db_add_artifact_to_collection"),
    ):
        loader.seed_from_artifacts(db, seeds_root)

    from services.platform_topology import _registry
    assert "authority" in _registry
    assert "agience/authority" in _registry
    inst_ns = loader.get_instance_namespace()
    expected = loader.derive_uuid(inst_ns, "agience", "authority")
    assert _registry["authority"] == expected


def test_seed_from_artifacts_uses_preregistered_id_over_uuid5(seeds_root, tmp_path, monkeypatch):
    """A platform id already resolved in the topology registry (e.g. persisted to
    settings at startup by pre_resolve_platform_ids) wins over uuid5 derivation —
    the loader converges on the same UUID the rest of the platform resolves via
    get_id(slug), rather than minting a parallel orphan."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    from services import platform_topology

    pinned = "99999999-9999-9999-9999-999999999999"
    platform_topology.register_id("authority", pinned)
    db = MagicMock()
    with (
        patch("services.seed_provisioning.loader.db_get_collection_by_id", return_value=None),
        patch("services.seed_provisioning.loader.db_create_collection"),
        patch("services.seed_provisioning.loader.db_get_artifact", return_value=None),
        patch("services.seed_provisioning.loader.db_create_artifact") as mock_create_art,
        patch("services.seed_provisioning.loader.db_add_artifact_to_collection"),
    ):
        loader.seed_from_artifacts(db, seeds_root)
    created_art = mock_create_art.call_args.args[1]
    assert created_art.id == pinned  # registered id, NOT uuid5-derived
