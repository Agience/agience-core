"""Declarative bootstrap artifact loader.

Replaces the imperative ``services/seed_provisioning/*.py`` modules with a
data-driven seed pipeline:

    seed_from_artifacts(arango_db, Path("/app/package/seeds")) → SeedReport

Each YAML/JSON file under ``package/seeds/<namespace>/`` declares a single
artifact (with optional ``edges:`` for containment + typed relations) or a
single grant. UUIDs derive deterministically from
``uuid5(instance_namespace, f"{namespace}/{slug}")`` so cross-artifact
references resolve without operator-typed UUIDs.

See ``.dev/features/declarative-bootstrap-artifacts.md`` for the full design.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from arango.database import StandardDatabase

from db.arango import (
    add_artifact_to_collection as db_add_artifact_to_collection,
    create_artifact as db_create_artifact,
    create_collection as db_create_collection,
    get_artifact as db_get_artifact,
    get_collection_by_id as db_get_collection_by_id,
    get_edge as db_get_edge,
    upsert_user_collection_grant as db_upsert_user_collection_grant,
)
from entities.artifact import Artifact as ArtifactEntity
from entities.collection import Collection as CollectionEntity, COLLECTION_CONTENT_TYPE
from kernel import config
from kernel.config import AGIENCE_PLATFORM_USER_ID
from services.platform_topology import get_id_optional, register_id

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    """Per-user context for user/admin-namespace seeds — resolved into
    ``{{user.*}}`` directives (principal, etc.). ``None`` for platform seeds."""

    id: str
    email: Optional[str] = None
    name: Optional[str] = None
    inbox_id: Optional[str] = None


# Grant action words → CRUDEASIO GrantEntity flags. Words (not letters) match
# the light-cone vocabulary in `services.dependencies._ACTION_FLAG_MAP`.
_ACTION_FLAG = {
    "create": "can_create",
    "read": "can_read",
    "update": "can_update",
    "delete": "can_delete",
    "evict": "can_evict",
    "add": "can_add",
    "share": "can_share",
    "invoke": "can_invoke",
    "admin": "can_admin",
}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@dataclass
class SeedReport:
    artifacts_added: int = 0
    artifacts_updated: int = 0
    artifacts_skipped: int = 0
    edges_added: int = 0
    edges_skipped: int = 0
    grants_added: int = 0
    grants_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"artifacts +{self.artifacts_added} ~{self.artifacts_updated} "
            f"={self.artifacts_skipped} | edges +{self.edges_added} "
            f"={self.edges_skipped} | grants +{self.grants_added} "
            f"={self.grants_skipped} | errors {len(self.errors)}"
        )


# ---------------------------------------------------------------------------
# Instance namespace
# ---------------------------------------------------------------------------


def _keys_dir() -> Path:
    """Read KEYS_DIR env at call time so tests can monkeypatch it."""
    val = os.getenv("KEYS_DIR")
    if val:
        return Path(val)
    from kernel import config
    return config.KEYS_DIR


def get_instance_namespace() -> uuid.UUID:
    """Return the per-deployment UUID4 used as the namespace for UUID5 derivation.

    Stored at ``$KEYS_DIR/instance.uuid`` and minted on first call. Idempotent.
    """
    path = _keys_dir() / "instance.uuid"
    if path.is_file():
        try:
            return uuid.UUID(path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            logger.warning("instance.uuid at %s was unreadable — rotating", path)
    new_ns = uuid.uuid4()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(new_ns), encoding="utf-8")
    logger.info("Minted new instance namespace %s at %s", new_ns, path)
    return new_ns


def derive_uuid(instance_namespace: uuid.UUID, namespace: str, slug: str) -> str:
    """uuid5(instance_namespace, f'{namespace}/{slug}') → str."""
    return str(uuid.uuid5(instance_namespace, f"{namespace}/{slug}"))


def _persist_seed_ids(arango_db: StandardDatabase, id_by_slug: dict[str, str]) -> None:
    """Persist freshly-derived slug→UUID mappings to ``platform_settings``
    (``platform.id.<slug>``), mirroring ``pre_resolve_platform_ids``. No-op when
    there is nothing new — keeps idempotent re-runs from touching the DB."""
    if not id_by_slug:
        return
    from services.platform_settings_service import settings as _settings

    _settings.set_many(
        arango_db,
        [{"key": f"platform.id.{slug}", "value": uid, "category": "platform"}
         for slug, uid in id_by_slug.items()],
    )


# ---------------------------------------------------------------------------
# Templating
# ---------------------------------------------------------------------------

# Directive syntax: {{directive.arg}} or {{directive:arg}} (both accepted).
# Examples:
#   {{config.AUTHORITY_ISSUER}}       — kernel.config attribute
#   {{file:manifest.json}}            — entire parsed file
#   {{file:manifest.json:trust_anchors}} — one key from the parsed file
_TEMPLATE_RE = re.compile(r"^\{\{(?P<directive>[a-z_]+)(?:[.:](?P<arg>[^}]+))?\}\}$")
# Reference shape: namespace/slug. Loader resolves these to UUIDs after templating.
_REF_RE = re.compile(r"^[a-z][a-z0-9_-]*\/[a-z0-9_/-]+$")


def _resolve_directive(
    value: str, instance_namespace: uuid.UUID, user: Optional[UserContext] = None
) -> Any:
    """Resolve a single ``{{directive[:arg]}}`` template.

    Templates only fire when the entire value is one directive. Half-templated
    strings (``"prefix-{{config.X}}"``) pass through unchanged so the loader
    stays predictable.
    """
    m = _TEMPLATE_RE.match(value)
    if not m:
        return value

    directive = m.group("directive")
    arg = m.group("arg") or ""

    if directive == "user":
        # {{user.id}} / {{user.email}} / {{user.inbox_id}} — only resolvable when
        # the loader runs with a user context (user-namespace seeds).
        if user is None:
            return None
        return getattr(user, arg.strip(), None)

    if directive == "config":
        attr = arg.strip()
        if not hasattr(config, attr):
            logger.warning("Template {{config.%s}} unresolved — kernel.config has no such attr", attr)
            return None
        return getattr(config, attr)

    if directive == "file":
        # arg is "PATH" or "PATH:KEY"
        path_part, _, key_part = arg.partition(":")
        path = _keys_dir() / path_part
        if not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Template {{file:%s}} unreadable", arg)
            return None
        if path.suffix.lower() in (".json", ".yaml", ".yml"):
            try:
                parsed = yaml.safe_load(text) if path.suffix.lower() in (".yaml", ".yml") else json.loads(text)
            except (yaml.YAMLError, json.JSONDecodeError):
                logger.warning("Template {{file:%s}} parse error", arg)
                return None
            if key_part:
                if isinstance(parsed, dict):
                    return parsed.get(key_part)
                return None
            return parsed
        # Raw file (non-JSON/YAML): no key extraction, return text.
        return text

    logger.warning("Template {{%s}} unrecognized directive", directive)
    return None


def _walk_resolve(
    node: Any,
    instance_namespace: uuid.UUID,
    refs: dict[str, str],
    user: Optional[UserContext] = None,
) -> Any:
    """Recursively resolve templates and references inside a parsed artifact.

    `refs` maps ``namespace/slug`` → UUID. Strings matching that shape become
    their UUID; strings matching ``{{...}}`` resolve via _resolve_directive.
    A ref missing from the local table falls back to the platform topology
    registry by slug, so per-user (later-run) seeds resolve platform refs
    seeded in the earlier DB-create run.
    """
    if isinstance(node, dict):
        return {k: _walk_resolve(v, instance_namespace, refs, user) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk_resolve(v, instance_namespace, refs, user) for v in node]
    if isinstance(node, str):
        if _TEMPLATE_RE.match(node):
            return _resolve_directive(node, instance_namespace, user)
        if _REF_RE.match(node):
            resolved = refs.get(node)
            if resolved is not None:
                return resolved
            # Cross-run fallback: resolve by slug via the topology registry.
            slug = node.split("/", 1)[1]
            return get_id_optional(slug) or node  # unresolved ref surfaces later
        return node
    return node


# ---------------------------------------------------------------------------
# Artifact discovery + parsing
# ---------------------------------------------------------------------------


@dataclass
class _RawArtifact:
    path: Path
    body: dict
    kind: str  # "artifact" | "grant"


def _parse_artifact_file(path: Path) -> Optional[_RawArtifact]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Artifact %s unreadable: %s", path, exc)
        return None
    try:
        body = yaml.safe_load(text) if path.suffix.lower() in (".yaml", ".yml") else json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        logger.warning("Artifact %s parse error: %s", path, exc)
        return None
    if not isinstance(body, dict):
        logger.warning("Artifact %s root must be a mapping", path)
        return None
    kind = body.get("type", "artifact")
    if kind not in ("artifact", "grant"):
        logger.warning("Artifact %s has unknown type %r — skipping", path, kind)
        return None
    return _RawArtifact(path=path, body=body, kind=kind)


def _discover_cards(seeds_root: Path) -> list[_RawArtifact]:
    if not seeds_root.is_dir():
        logger.info("Artifacts root %s does not exist — no artifacts to load", seeds_root)
        return []
    artifacts: list[_RawArtifact] = []
    for path in sorted(seeds_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".yaml", ".yml", ".json"):
            continue
        # Skip files that are clearly not artifacts (manifest, schema, etc.)
        if path.name.startswith("_"):
            continue
        artifact = _parse_artifact_file(path)
        if artifact is not None:
            artifacts.append(artifact)
    return artifacts


# ---------------------------------------------------------------------------
# Artifact application
# ---------------------------------------------------------------------------


def _is_collection_content_type(content_type: str) -> bool:
    """Decide whether to write to the `collections` table vs `artifacts`.

    The unified-store model treats them as the same logical entity, but the
    schema currently has separate physical collections. We route based on the
    canonical collection MIME (and the workspace MIME, which inherits).
    """
    return content_type in (
        COLLECTION_CONTENT_TYPE,
        "application/vnd.agience.workspace+json",
    )


def _primary_collection_id(body: dict) -> Optional[str]:
    """Return the container UUID from this artifact's origin containment edge,
    so the seeded artifact's ``collection_id`` is populated (several queries
    filter on it). Edge ``to`` targets are already resolved to UUIDs by the
    time this runs. Returns None if the artifact has no origin containment edge.
    """
    for edge in body.get("edges") or []:
        if edge.get("rel", "contained_by") == "contained_by" and edge.get("origin", True):
            target = edge.get("to")
            if isinstance(target, str) and "/" not in target:
                return target
    return None


def _apply_artifact_card(
    arango_db: StandardDatabase,
    artifact: _RawArtifact,
    artifact_uuid: str,
    report: SeedReport,
) -> None:
    body = artifact.body
    namespace = body["namespace"]
    slug = body["slug"]
    content_type = body.get("content_type", "application/json")
    name = body.get("name", slug)
    description = body.get("description", "")
    context = body.get("context") or {}
    content = body.get("content", "")

    now = datetime.now(timezone.utc).isoformat()

    if _is_collection_content_type(content_type):
        existing = db_get_collection_by_id(arango_db, artifact_uuid)
        if existing:
            report.artifacts_skipped += 1
            return
        try:
            collection = CollectionEntity(
                id=artifact_uuid,
                name=name,
                description=description,
                created_by=AGIENCE_PLATFORM_USER_ID,
                content_type=content_type,
                state=CollectionEntity.STATE_COMMITTED,
                created_time=now,
                modified_time=now,
            )
            db_create_collection(arango_db, collection)
            report.artifacts_added += 1
            logger.info("Seeded collection %s/%s (id=%s)", namespace, slug, artifact_uuid)
        except Exception as exc:
            report.errors.append(f"{artifact.path}: {exc}")
            logger.exception("Failed to create collection from artifact %s", artifact.path)
        return

    # Artifact path
    existing = db_get_artifact(arango_db, artifact_uuid)
    if existing:
        report.artifacts_skipped += 1
        return
    try:
        artifact = ArtifactEntity(
            id=artifact_uuid,
            root_id=artifact_uuid,
            collection_id=_primary_collection_id(body),
            state=ArtifactEntity.STATE_COMMITTED,
            context=json.dumps(context, separators=(",", ":"), ensure_ascii=False) if isinstance(context, (dict, list)) else context,
            content=content,
            content_type=content_type,
            created_by=AGIENCE_PLATFORM_USER_ID,
            created_time=now,
        )
        db_create_artifact(arango_db, artifact)
        report.artifacts_added += 1
        logger.info("Seeded artifact %s/%s (id=%s)", namespace, slug, artifact_uuid)
    except Exception as exc:
        report.errors.append(f"{artifact.path}: {exc}")
        logger.exception("Failed to create artifact from artifact %s", artifact.path)


def _apply_edges(
    arango_db: StandardDatabase,
    artifact: _RawArtifact,
    artifact_uuid: str,
    refs: dict[str, str],
    report: SeedReport,
) -> None:
    body = artifact.body
    edges = body.get("edges") or []
    if not edges:
        return
    for edge in edges:
        rel = edge.get("rel", "contained_by")
        target_ref = edge.get("to")
        if not isinstance(target_ref, str):
            report.errors.append(f"{artifact.path}: edge missing `to`")
            continue
        target_uuid = refs.get(target_ref, target_ref)
        if "/" in str(target_uuid):
            report.errors.append(f"{artifact.path}: unresolved edge target {target_ref!r}")
            continue

        origin = bool(edge.get("origin", rel == "contained_by"))
        propagate = edge.get("propagate")    # full action words; None = all actions
        order_key = edge.get("order_key")

        # Containment edge: container(_from) → child(_to). A typed (non-containment)
        # edge originates FROM this artifact: this(_from) → target(_to), labelled
        # with `relationship`. Typed edges don't pollute containment traversals,
        # which filter `relationship == null`.
        if rel == "contained_by":
            container, child, relationship = target_uuid, artifact_uuid, None
        else:
            container, child, relationship = artifact_uuid, target_uuid, rel

        # Idempotency + order_key preservation: never overwrite an existing edge
        # (add_artifact_to_collection upserts with overwrite=True, which would
        # reset order_key and clobber user/operator reordering on re-seed).
        if db_get_edge(arango_db, container, child):
            report.edges_skipped += 1
            continue
        try:
            db_add_artifact_to_collection(
                arango_db, container, child, order_key,
                origin=origin, propagate=propagate, relationship=relationship,
            )
            report.edges_added += 1
        except Exception as exc:
            report.errors.append(f"{artifact.path}: edge {rel}->{target_ref}: {exc}")
            logger.exception("Edge add failed (%s -> %s)", container, child)


def _resolve_grant_card(
    artifact: _RawArtifact,
    report: SeedReport,
) -> list[tuple[str, str, dict, Optional[str]]]:
    """Resolve a ``type: grant`` artifact to ``(principal, resource, flags, name)``
    tuples (one per resource). Returns ``[]`` when invalid (recording the reason).
    Body fields (already ref/template-resolved): ``principal`` (uuid), ``resource``
    (uuid) or ``resources`` (list of uuids), ``actions`` (full action words),
    optional ``name``. Grants are uniform — no conditions, no operator type; which
    grants a principal receives is decided by which seed set is applied to them."""
    body = artifact.body
    principal = body.get("principal")
    if not isinstance(principal, str) or not principal or "/" in principal:
        report.errors.append(f"{artifact.path}: unresolved grant principal {body.get('principal')!r}")
        return []

    resources = body.get("resources")
    if resources is None and body.get("resource") is not None:
        resources = [body.get("resource")]
    if not isinstance(resources, list) or not resources:
        report.errors.append(f"{artifact.path}: grant missing resource(s)")
        return []

    flags = {flag: False for flag in _ACTION_FLAG.values()}
    for action in body.get("actions") or []:
        flag = _ACTION_FLAG.get(action)
        if flag is None:
            report.errors.append(f"{artifact.path}: unknown grant action {action!r}")
            continue
        flags[flag] = True

    name = body.get("name")
    out: list[tuple[str, str, dict, Optional[str]]] = []
    for res in resources:
        if not isinstance(res, str) or not res or "/" in res:
            report.errors.append(f"{artifact.path}: unresolved grant resource {res!r}")
            continue
        out.append((principal, res, flags, name))
    return out


def _apply_accumulated_grants(
    arango_db: StandardDatabase,
    accumulated: dict,
    report: SeedReport,
) -> None:
    """Upsert the unioned grants — one write per ``(principal, resource)``."""
    for (principal, resource), spec in accumulated.items():
        try:
            _grant, changed = db_upsert_user_collection_grant(
                arango_db,
                user_id=principal,
                collection_id=resource,
                granted_by=AGIENCE_PLATFORM_USER_ID,
                name=spec["name"],
                **spec["flags"],
            )
            report.grants_added += 1 if changed else 0
            report.grants_skipped += 0 if changed else 1
        except Exception as exc:
            report.errors.append(f"grant insert failed ({principal} -> {resource}): {exc}")
            logger.exception("Grant insert failed (%s -> %s)", principal, resource)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def seed_from_artifacts(
    arango_db: StandardDatabase,
    seeds_root: Path,
    *,
    user: Optional[UserContext] = None,
) -> SeedReport:
    """Idempotently apply every artifact under ``seeds_root`` to the database.

    Order of application:
      1. All artifacts across namespaces (insert if absent), identity resolved.
      2. Templates + refs resolved per body; artifacts written.
      3. Edges (containment + typed) applied with attributes.
      4. Grants applied (idempotent user→resource upserts).

    ``user`` carries the per-user context for user-namespace seeds (resolves
    ``{{user.*}}`` directives and gates ``condition`` blocks). ``None`` for
    platform seeds. Returns a SeedReport summarizing what changed.
    """
    report = SeedReport()
    artifacts = _discover_cards(seeds_root)
    if not artifacts:
        logger.info("No artifacts found under %s", seeds_root)
        return report

    instance_namespace = get_instance_namespace()

    # First pass: build the refs table for ALL artifacts (so edge/grant targets
    # resolve regardless of file order).
    refs: dict[str, str] = {}
    new_ids: dict[str, str] = {}
    artifact_cards: list[_RawArtifact] = []
    grant_cards: list[_RawArtifact] = []
    for artifact in artifacts:
        if artifact.kind == "grant":
            grant_cards.append(artifact)
            continue
        ns = artifact.body.get("namespace")
        slug = artifact.body.get("slug")
        if not ns or not slug:
            report.errors.append(f"{artifact.path}: artifact missing namespace or slug")
            continue
        # Per-user artifacts may template the slug (e.g. ``inbox-{{user.id}}``);
        # resolve it before deriving identity so each user gets a distinct UUID.
        if isinstance(slug, str) and _TEMPLATE_RE.match(slug):
            resolved_slug = _resolve_directive(slug, instance_namespace, user)
            if not isinstance(resolved_slug, str) or not resolved_slug:
                report.errors.append(f"{artifact.path}: slug template did not resolve: {slug!r}")
                continue
            slug = resolved_slug
            artifact.body["slug"] = slug
        ref = f"{ns}/{slug}"
        # Identity: a platform id already resolved at startup (by
        # platform_topology.pre_resolve_platform_ids, or a prior loader run)
        # wins, so the loader converges on the same UUID the rest of the
        # platform resolves via get_id(slug). A brand-new slug derives a
        # deterministic uuid5 from the per-install instance namespace and is
        # persisted below so it survives restarts.
        existing_id = get_id_optional(slug)
        if existing_id:
            artifact_uuid = existing_id
        else:
            artifact_uuid = derive_uuid(instance_namespace, ns, slug)
            new_ids[slug] = artifact_uuid
        refs[ref] = artifact_uuid
        # Register the slug so existing `get_id(<slug>)` callers keep working.
        register_id(slug, artifact_uuid)
        register_id(ref, artifact_uuid)
        artifact_cards.append(artifact)

    # Persist freshly-derived slug→UUID mappings to platform_settings so the
    # loader is the durable ID authority (pre_resolve_platform_ids reloads them
    # on the next boot, and the per-user run resolves platform refs via them).
    _persist_seed_ids(arango_db, new_ids)

    # Second pass: resolve templates + references in artifact bodies, then apply.
    for artifact in artifact_cards:
        ns = artifact.body["namespace"]
        slug = artifact.body["slug"]
        artifact_uuid = refs[f"{ns}/{slug}"]
        artifact.body = _walk_resolve(artifact.body, instance_namespace, refs, user)
        _apply_artifact_card(arango_db, artifact, artifact_uuid, report)

    # Third pass: apply edges (artifacts now exist).
    for artifact in artifact_cards:
        ns = artifact.body["namespace"]
        slug = artifact.body["slug"]
        artifact_uuid = refs[f"{ns}/{slug}"]
        _apply_edges(arango_db, artifact, artifact_uuid, refs, report)

    # Fourth pass: grants. Resolve each card, then accumulate by
    # (principal, resource) with flag UNION — grants are grants, so a principal's
    # grant on a resource is the union of every matching declaration. Order is
    # irrelevant and operator/user grants compose (e.g. a base read + an
    # operator-conditioned admin yield read+admin).
    accumulated: dict = {}
    for artifact in grant_cards:
        artifact.body = _walk_resolve(artifact.body, instance_namespace, refs, user)
        for principal, resource, flags, name in _resolve_grant_card(artifact, report):
            key = (principal, resource)
            if key in accumulated:
                spec = accumulated[key]
                spec["flags"] = {f: spec["flags"][f] or flags[f] for f in flags}
                spec["name"] = spec["name"] or name
            else:
                accumulated[key] = {"flags": dict(flags), "name": name}
    _apply_accumulated_grants(arango_db, accumulated, report)

    logger.info("Seed report: %s", report.summary())
    if report.errors:
        for err in report.errors:
            logger.warning("seed-from-artifacts: %s", err)
    return report
