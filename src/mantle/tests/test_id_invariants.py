"""
ID invariant tests -- codifies the platform's identity model rules.

These tests make the following design decisions explicit and regression-proof:

1. Personal collection ID == user UUID (intentional convenience)
2. Inbox workspace ID == user UUID (intentional convenience)
3. All platform bootstrap IDs are UUIDs (not readable strings)
4. Platform topology registry maps slugs to UUIDs
"""

import re
import uuid
from unittest.mock import MagicMock, patch

import pytest

from services.bootstrap_types import ALL_PLATFORM_COLLECTION_SLUGS
from services.platform_topology import (
    clear_registry,
    get_all_platform_collection_ids,
    get_id,
    register_id,
)

UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


# ---------------------------------------------------------------------------
# Personal collection / inbox workspace: ID == user_id (intentional)
# ---------------------------------------------------------------------------


@patch("db.arango.upsert_user_collection_grant")
@patch("services.collection_service.ensure_collection_descriptor")
@patch("services.collection_service.db_create_collection")
def test_personal_collection_id_equals_user_id(mock_create, _mock_descriptor, _mock_grant):
    """
    Design decision: personal collection ID is set to the user UUID.
    This is intentional -- both the collection and the user share the same UUID.
    """
    from services.collection_service import create_new_collection

    mock_create.side_effect = lambda db, entity: entity
    user_id = str(uuid.uuid4())

    result = create_new_collection(
        db=MagicMock(),
        owner_id=user_id,
        name="Personal",
        description="Test personal collection",
        is_personal=True,
    )

    assert result.id == user_id, (
        "Personal collection ID must equal the user UUID. "
        "This is an intentional design convention, not a bug."
    )


# ---------------------------------------------------------------------------
# Platform topology registry
# ---------------------------------------------------------------------------


def test_get_id_raises_before_registration():
    """Registry must raise RuntimeError for unknown slugs."""
    clear_registry()
    with pytest.raises(RuntimeError, match="not registered"):
        get_id("nonexistent-slug")


def test_register_and_get_id_roundtrip():
    """Register a slug->UUID, then get_id returns the same UUID."""
    clear_registry()
    test_uuid = str(uuid.uuid4())
    register_id("test-slug", test_uuid)
    assert get_id("test-slug") == test_uuid


def test_get_all_platform_collection_ids_returns_uuids():
    """After registration, all platform collection IDs must be valid UUIDs."""
    clear_registry()
    for slug in ALL_PLATFORM_COLLECTION_SLUGS:
        register_id(slug, str(uuid.uuid4()))

    ids = get_all_platform_collection_ids()
    assert len(ids) == len(ALL_PLATFORM_COLLECTION_SLUGS)
    for collection_id in ids:
        assert UUID_REGEX.match(collection_id), (
            f"Platform collection ID '{collection_id}' is not a valid UUID"
        )


# Platform bootstrap now creates UUID-id collections + artifacts via the
# declarative loader; that is asserted end-to-end in test_seed_platform_tree.py
# (every seeded collection/artifact id is a deterministic uuid5).
