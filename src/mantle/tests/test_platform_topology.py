"""Unit tests for services.platform_topology.

The runtime slug → UUID registry that the entire platform depends on for
collection lookups during request handling. Strict get_id() must raise on a
missing slug; get_id_optional() must return None. pre_resolve_platform_ids()
must register every category of slug (collections, singleton artifacts, agents,
LLM connections, MCP servers).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from services import platform_topology as pt
from services.bootstrap_types import (
    ALL_PLATFORM_COLLECTION_SLUGS,
    AUTHORITY_ARTIFACT_SLUG,
)


@pytest.fixture
def empty_registry():
    """Snapshot + clear before, restore after — keeps tests hermetic without
    breaking other tests that rely on the autouse conftest seeding."""
    snap = dict(pt._registry)
    pt.clear_registry()
    yield
    pt._registry.clear()
    pt._registry.update(snap)


class TestRegistryBasics:
    def test_register_and_get(self, empty_registry):
        pt.register_id("slug-a", "uuid-a")
        assert pt.get_id("slug-a") == "uuid-a"
        assert pt.get_id_optional("slug-a") == "uuid-a"

    def test_get_strict_raises_on_missing(self, empty_registry):
        with pytest.raises(RuntimeError, match="not registered"):
            pt.get_id("missing")

    def test_get_optional_returns_none_on_missing(self, empty_registry):
        assert pt.get_id_optional("missing") is None

    def test_clear_registry_empties(self, empty_registry):
        pt.register_id("a", "1")
        pt.clear_registry()
        assert pt.get_id_optional("a") is None

    def test_register_overwrites(self, empty_registry):
        pt.register_id("slug-a", "uuid-1")
        pt.register_id("slug-a", "uuid-2")
        assert pt.get_id("slug-a") == "uuid-2"

    def test_get_all_platform_collection_ids_returns_one_per_slug(self, empty_registry):
        for slug in ALL_PLATFORM_COLLECTION_SLUGS:
            pt.register_id(slug, str(uuid.uuid4()))
        ids = pt.get_all_platform_collection_ids()
        assert len(ids) == len(ALL_PLATFORM_COLLECTION_SLUGS)
        # All IDs distinct
        assert len(set(ids)) == len(ids)


class TestPreResolvePlatformIds:
    def test_uses_existing_settings_ids_when_present(self, empty_registry):
        """When platform_settings has persisted slug→UUID mappings,
        pre_resolve picks them up without generating new IDs."""
        existing_id = "existing-persisted-id"

        mock_settings = MagicMock()
        mock_settings.get.return_value = existing_id
        mock_settings.set_many = MagicMock()

        with patch("services.platform_settings_service.settings", mock_settings):
            pt.pre_resolve_platform_ids(MagicMock())

        # All collection slugs picked up the persisted ID.
        for slug in ALL_PLATFORM_COLLECTION_SLUGS:
            assert pt.get_id(slug) == existing_id

        # The authority/host artifact slugs picked up the persisted ID.
        assert pt.get_id(AUTHORITY_ARTIFACT_SLUG) == existing_id

        # No new settings were written since all were found.
        mock_settings.set_many.assert_not_called()

    def test_leaves_missing_slugs_unregistered(self, empty_registry):
        """Fallback-only: pre_resolve never mints IDs. A slug with no persisted
        mapping stays unregistered — the declarative seed loader derives and
        persists it on the fresh-DB bootstrap run (and the platform trigger then
        re-runs server_registry.populate_ids)."""
        mock_settings = MagicMock()
        mock_settings.get.return_value = None
        mock_settings.set_many = MagicMock()

        with patch("services.platform_settings_service.settings", mock_settings):
            pt.pre_resolve_platform_ids(MagicMock())

        for slug in ALL_PLATFORM_COLLECTION_SLUGS:
            assert pt.get_id_optional(slug) is None
        mock_settings.set_many.assert_not_called()
