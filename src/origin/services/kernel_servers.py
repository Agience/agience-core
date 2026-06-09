"""Kernel server client_id resolution for Origin's `_require_kernel_server` guards.

Origin's internal endpoints (`/internal/persons/{id}`, `/internal/delegation-token`,
etc.) accept calls only from kernel servers — that is, first-party MCP persona
servers (defined in `chorus/manifest.json`) plus the `agience-mantle` artifact
service.

This module reads `chorus/manifest.json` once at import time and exposes
`all_client_ids()` returning the set of accepted persona client IDs. The
caller adds `agience-mantle` separately when needed.

Mirrors `mantle/services/server_registry._load_manifest` but ships only the
client_id list — Origin doesn't instantiate any chorus servers, it just gates
on identity.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import FrozenSet

logger = logging.getLogger(__name__)


def _load_client_ids() -> FrozenSet[str]:
    """Read `chorus/manifest.json` and return the set of `agience-server-{name}` IDs."""
    candidates = [
        Path(__file__).resolve().parents[3] / "chorus" / "manifest.json",   # repo dev layout
        Path("/chorus/manifest.json"),                                       # Docker layout
    ]
    raw = None
    for p in candidates:
        if p.is_file():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                break
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("kernel_servers: failed to parse %s: %s", p, exc)
    if raw is None:
        logger.warning(
            "kernel_servers: chorus/manifest.json not found; kernel set will be empty"
        )
        return frozenset()
    ids: list[str] = []
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else None
        if not name:
            continue
        ids.append(f"agience-server-{name}")
    return frozenset(ids)


_CLIENT_IDS: FrozenSet[str] = _load_client_ids()


def all_client_ids() -> FrozenSet[str]:
    """Return the cached set of first-party persona client IDs."""
    return _CLIENT_IDS
