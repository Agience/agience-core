# /entities/collection.py
#
# Container-as-artifact: a workspace IS a collection IS an artifact.
# The Collection class is an alias for Artifact. All container docs
# live in the `artifacts` ArangoDB collection, discriminated by content_type.
#
# See .dev/features/container-as-artifact.md.

from entities.artifact import (
    Artifact,
    WORKSPACE_CONTENT_TYPE,
    COLLECTION_CONTENT_TYPE,
)

Collection = Artifact

__all__ = [
    "Collection",
    "WORKSPACE_CONTENT_TYPE",
    "COLLECTION_CONTENT_TYPE",
]
