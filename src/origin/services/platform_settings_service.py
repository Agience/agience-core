"""Origin platform settings — DB-backed (Postgres) with in-memory cache.

Mirrors the API surface of Mantle's `services/platform_settings_service.py` so
calling code is portable. Secrets are stored encrypted in the `secret_value`
column (Fernet) and decrypted on read. Plain settings live in `value`.

`load_all(session)` populates the cache at startup. `set_value()` writes through
to Postgres + cache. `needs_setup()` is true until `platform.setup_complete`
flips to "true".
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from kernel.key_manager import get_encryption_key
from origin.db import platform_settings as db_settings
from origin.models.platform_setting import PlatformSetting

logger = logging.getLogger(__name__)


# Defaults — used when no DB row exists. Mirrors Mantle's defaults but trimmed
# to settings Origin actually consumes.
DEFAULTS: dict[str, str] = {
    "platform.setup_complete": "false",
    "branding.facet_uri": "http://localhost:5173",
    "branding.title": "Agience",
    "auth.password.enabled": "true",
    "auth.password.min_length": "12",
    "auth.password.pbkdf2_iters": "200000",
    "auth.invite_only": "false",
    "platform.log_level": "info",
    "email.provider": "",
    "email.from_address": "",
    "email.from_name": "Agience",
}


class _SettingsCache:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._secrets: dict[str, str] = {}

    def load_all(self, db: Session) -> None:
        self._values.clear()
        self._secrets.clear()
        for row in db_settings.list_all(db):
            self._absorb(row)
        logger.info(
            "Origin: loaded %d platform setting(s) (%d secret) from Postgres",
            len(self._values) + len(self._secrets),
            len(self._secrets),
        )

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if key in self._values:
            return self._values[key]
        return DEFAULTS.get(key, default)

    def get_secret(self, key: str) -> Optional[str]:
        return self._secrets.get(key)

    def get_int(self, key: str, default: int = 0) -> int:
        raw = self.get(key)
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def needs_setup(self) -> bool:
        return self.get("platform.setup_complete", "false") != "true"

    def set_value(
        self,
        db: Session,
        key: str,
        raw: Optional[str],
        *,
        is_secret: bool = False,
        category: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> None:
        if is_secret:
            ciphertext = _fernet().encrypt((raw or "").encode("utf-8")).decode("ascii")
            db_settings.set_value(
                db,
                key,
                value=None,
                secret_value=ciphertext,
                is_secret=True,
                category=category,
                updated_by=updated_by,
            )
            self._secrets[key] = raw or ""
            self._values.pop(key, None)
        else:
            db_settings.set_value(
                db,
                key,
                value=raw,
                secret_value=None,
                is_secret=False,
                category=category,
                updated_by=updated_by,
            )
            self._values[key] = raw or ""
            self._secrets.pop(key, None)
        db.commit()

    def set_many(
        self,
        db: Session,
        items: Iterable[dict],
        *,
        updated_by: Optional[str] = None,
    ) -> int:
        count = 0
        for item in items:
            self.set_value(
                db,
                item["key"],
                item.get("value"),
                is_secret=item.get("is_secret", False),
                category=item.get("category"),
                updated_by=updated_by,
            )
            count += 1
        return count

    def _absorb(self, row: PlatformSetting) -> None:
        if row.is_secret and row.secret_value:
            try:
                self._secrets[row.key] = _fernet().decrypt(row.secret_value.encode("ascii")).decode("utf-8")
            except Exception:
                logger.warning("Failed to decrypt secret %s — ignoring stored value", row.key)
        elif not row.is_secret and row.value is not None:
            self._values[row.key] = row.value


def _fernet() -> Fernet:
    return Fernet(get_encryption_key().encode())


# Singleton — imported as `from origin.services.platform_settings_service import settings`
settings = _SettingsCache()
