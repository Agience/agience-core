import json
import uuid
from unittest.mock import MagicMock, patch

from services import host_content_service as svc
from services.bootstrap_types import (
    AUTHORITY_ARTIFACT_SLUG,
    AUTHORITY_COLLECTION_SLUG,
    HOST_ARTIFACT_SLUG,
    HOST_COLLECTION_SLUG,
)
from services.platform_topology import clear_registry, register_id


def _setup_registry():
    """Populate the platform topology registry with test UUIDs."""
    clear_registry()
    register_id(HOST_COLLECTION_SLUG, str(uuid.uuid4()))
    register_id(HOST_ARTIFACT_SLUG, str(uuid.uuid4()))
    register_id(AUTHORITY_ARTIFACT_SLUG, str(uuid.uuid4()))
    register_id(AUTHORITY_COLLECTION_SLUG, str(uuid.uuid4()))


@patch("services.host_content_service.ensure_collection_descriptor")
@patch("services.host_content_service.db_add_artifact_to_collection")
@patch("services.host_content_service.db_create_artifact")
@patch("services.host_content_service.db_create_collection")
@patch("services.host_content_service.db_get_artifact", return_value=None)
@patch("services.host_content_service.db_get_artifact_by_collection_and_root", return_value=None)
@patch("services.host_content_service.db_get_collection_by_id", return_value=None)
def test_ensure_current_instance_host_creates_collection_and_artifact(
    _mock_get_collection,
    _mock_get_linked,
    _mock_get_artifact,
    mock_create_collection,
    mock_create_artifact,
    mock_add_artifact,
    _mock_ensure_descriptor,
):
    _setup_registry()
    result = svc.ensure_current_instance_host(MagicMock())

    # Result is a UUID, not a readable string
    assert result is not None
    uuid.UUID(result)
    assert mock_create_collection.called
    assert mock_create_artifact.called
    mock_add_artifact.assert_called_once()


@patch("services.host_content_service.db_add_artifact_to_collection")
@patch("services.host_content_service.db_create_artifact")
@patch("services.host_content_service.db_create_collection")
@patch("services.host_content_service.db_get_artifact_by_collection_and_root", return_value=object())
@patch("services.host_content_service.db_get_collection_by_id")
def test_ensure_current_instance_host_is_noop_when_link_exists(
    mock_get_collection,
    _mock_get_linked,
    mock_create_collection,
    mock_create_artifact,
    mock_add_artifact,
):
    _setup_registry()
    existing_col = MagicMock()
    existing_col.id = str(uuid.uuid4())
    mock_get_collection.return_value = existing_col

    result = svc.ensure_current_instance_host(MagicMock())

    assert result == existing_col.id
    mock_create_collection.assert_not_called()
    mock_create_artifact.assert_not_called()
    mock_add_artifact.assert_not_called()


def test_build_current_instance_host_context_contains_host_metadata():
    _setup_registry()
    context = json.loads(svc._build_current_instance_host_context())

    assert context["type"] == "host"
    assert context["content_type"] == svc.HOST_CONTENT_TYPE
    # authority references should be UUIDs
    uuid.UUID(context["authority"]["artifact_id"])
    uuid.UUID(context["authority"]["collection_id"])
    assert context["host"]["scope"] == "current-instance"
    assert context["host"]["install"]["owner_repo"] is True


@patch("services.host_content_service.db_upsert_user_collection_grant")
def test_grant_host_collection_to_user_upserts_read_grant(mock_upsert):
    mock_upsert.return_value = (MagicMock(), True)
    _setup_registry()
    svc.grant_host_collection_to_user(MagicMock(), "user-123")

    mock_upsert.assert_called_once()
    kwargs = mock_upsert.call_args.kwargs
    uuid.UUID(kwargs["collection_id"])
    assert kwargs["can_read"] is True
    assert kwargs["can_update"] is False  # default: read-only for non-operators


@patch("services.host_content_service.db_upsert_user_collection_grant")
def test_grant_host_collection_to_user_write_access_for_operator(mock_upsert):
    mock_upsert.return_value = (MagicMock(), True)
    _setup_registry()
    svc.grant_host_collection_to_user(MagicMock(), "operator-123", can_update=True)

    mock_upsert.assert_called_once()
    kwargs = mock_upsert.call_args.kwargs
    assert kwargs["can_read"] is True
    assert kwargs["can_update"] is True
