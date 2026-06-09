"""Manifest loader — declarative platform state.

Replaces the cross-service bootstrap callback design. A single optional
YAML file at `${DATA_PATH}/manifest.yml` (or path passed in) declares
platform state. Each service applies its own section idempotently on
startup. If absent, services come up empty and the setup wizard handles
configuration interactively.

Origin applies these sections (this file):
- `operator` — first-boot operator account (Person + admin grants)
- `platform_settings` — DB-backed settings (plain + secret)
- `grants` — explicit user→resource grants by `resource_id` (UUID)

Other sections (intentionally not applied here):
- `seed_collections` — Mantle's responsibility
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from origin.db import persons as db_persons
from origin.services import auth_service as origin_auth
from origin.services import grant_service as origin_grants
from origin.services.platform_settings_service import settings as platform_settings

logger = logging.getLogger(__name__)


def manifest_path() -> Path:
    """Default manifest location. Override with `MANIFEST_PATH` env."""
    explicit = os.getenv("MANIFEST_PATH")
    if explicit:
        return Path(explicit)
    data_path = os.getenv("DATA_PATH", "/data")
    return Path(data_path) / "manifest.yml"


def load(path: Path | None = None) -> dict[str, Any]:
    """Read + parse the manifest. Returns `{}` when missing or empty."""
    p = path or manifest_path()
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("manifest %s could not be parsed: %s", p, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("manifest %s root is not a mapping", p)
        return {}
    return data


def apply(db: Session, manifest: dict[str, Any]) -> dict[str, int]:
    """Idempotently apply Origin's sections of a manifest.

    Returns a counts dict for the operator's audit log:
    `{operator_created, settings_written, grants_upserted}`.
    """
    counts = {"operator_created": 0, "settings_written": 0, "grants_upserted": 0}

    operator = manifest.get("operator") or {}
    if isinstance(operator, dict) and operator.get("email"):
        if _ensure_operator(db, operator):
            counts["operator_created"] = 1

    settings_section = manifest.get("platform_settings") or {}
    if isinstance(settings_section, dict) and settings_section:
        counts["settings_written"] = _apply_platform_settings(db, settings_section)

    grants_section = manifest.get("grants") or []
    if isinstance(grants_section, list) and grants_section:
        counts["grants_upserted"] = _apply_grants(db, grants_section)

    if any(counts.values()):
        logger.info("manifest applied: %s", counts)
    return counts


def _ensure_operator(db: Session, operator: dict) -> bool:
    """Create the operator Person if no one with this email exists yet."""
    email = (operator.get("email") or "").strip().lower()
    if not email:
        return False
    existing = db_persons.get_by_email(db, email)
    if existing:
        # Stamp operator_id on platform_settings (idempotent).
        platform_settings.set_value(
            db,
            "platform.operator_id",
            str(existing.id),
            is_secret=False,
            category="platform",
        )
        return False

    raw_password = operator.get("password")
    password_hash = operator.get("password_hash")
    if raw_password and not password_hash:
        password_hash = origin_auth.hash_password(raw_password)

    name = operator.get("name") or email.split("@")[0]
    person = db_persons.create(
        db,
        {
            "email": email,
            "name": name,
            "username": name,
            "password_hash": password_hash,
        },
    )
    db.flush()
    platform_settings.set_value(
        db,
        "platform.operator_id",
        str(person.id),
        is_secret=False,
        category="platform",
    )
    logger.info("manifest: created operator %s (%s)", person.id, email)
    return True


def _apply_platform_settings(db: Session, settings_section: dict) -> int:
    """Write each `key: value` pair to platform_settings.

    Keys with `_secret` suffix are stored encrypted (e.g.
    `auth.google.client_secret`). The convention: a key whose name contains
    `secret`, `password`, `api_key`, `token`, or `credential` is encrypted.
    """
    secret_markers = ("secret", "password", "api_key", "token", "credential")
    written = 0
    for raw_key, raw_value in settings_section.items():
        key = str(raw_key)
        value = str(raw_value) if raw_value is not None else ""
        is_secret = any(marker in key.lower() for marker in secret_markers)
        category = key.split(".")[0] if "." in key else "platform"
        platform_settings.set_value(
            db,
            key,
            value,
            is_secret=is_secret,
            category=category,
        )
        written += 1
    return written


def _apply_grants(db: Session, grants_section: list) -> int:
    """Apply explicit user→resource grants. `resource_id` is a UUID."""
    upserted = 0
    operator_id = platform_settings.get("platform.operator_id")

    for entry in grants_section:
        if not isinstance(entry, dict):
            continue
        resource_id = entry.get("resource_id")
        grantee_id = entry.get("grantee_id")
        grantee_email = entry.get("grantee_email")
        role = entry.get("role")

        if not resource_id:
            logger.warning("manifest grant skipped (no resource_id): %s", entry)
            continue
        if not grantee_id and grantee_email:
            person = db_persons.get_by_email(db, grantee_email)
            if person is None:
                logger.warning("manifest grant skipped — grantee %s not found", grantee_email)
                continue
            grantee_id = str(person.id)
        if not grantee_id:
            continue

        flags = (
            origin_grants.permissions_for_role(role) if role else _flags_from_entry(entry)
        )
        granted_by = entry.get("granted_by") or operator_id or grantee_id
        _grant, changed = origin_grants.upsert_user_grant(
            db,
            user_id=grantee_id,
            resource_id=resource_id,
            granted_by=granted_by,
            flags=flags,
            name=entry.get("name") or "Manifest grant",
        )
        if changed:
            upserted += 1
    return upserted


def _flags_from_entry(entry: dict) -> dict:
    flag_keys = (
        "can_create",
        "can_read",
        "can_update",
        "can_delete",
        "can_evict",
        "can_invoke",
        "can_add",
        "can_share",
        "can_admin",
    )
    return {f: bool(entry.get(f, False)) for f in flag_keys}
