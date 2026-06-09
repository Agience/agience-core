"""Declarative platform + per-user provisioning.

Platform bootstrap (collections, authority, host, agents, agency, MCP servers,
LLM connections, package registry, inbox seeds + onboarding content) is data:
YAML/JSON artifacts under ``package/seeds/platform``, applied idempotently by
:func:`seed_from_artifacts`. Per-user first-login provisioning is
:func:`provision_user` — the declarative grant seeds under ``package/seeds/user``
(templated with the user's id) plus thin runtime glue that ensures the user's
Inbox workspace and materializes curated seed artifacts into it.

There is a single bootstrap path: the loader. The former per-module imperative
seeders are gone.
"""

from .loader import (
    SeedReport,
    UserContext,
    derive_uuid,
    get_instance_namespace,
    seed_from_artifacts,
)
from .user_provisioning import provision_user

__all__ = [
    "SeedReport",
    "UserContext",
    "derive_uuid",
    "get_instance_namespace",
    "seed_from_artifacts",
    "provision_user",
]
