import json
import uuid
from unittest.mock import MagicMock, patch

from services import authority_content_service as svc
from services.bootstrap_types import (
    AUTHORITY_ARTIFACT_SLUG,
    AUTHORITY_COLLECTION_SLUG,
    HOST_ARTIFACT_SLUG,
)
from services.platform_topology import clear_registry, register_id


def _setup_registry():
    """Populate the platform topology registry with test UUIDs."""
    clear_registry()
    register_id(AUTHORITY_COLLECTION_SLUG, str(uuid.uuid4()))
    register_id(AUTHORITY_ARTIFACT_SLUG, str(uuid.uuid4()))
    register_id(HOST_ARTIFACT_SLUG, str(uuid.uuid4()))


@patch("services.authority_content_service.ensure_collection_descriptor")
@patch("services.authority_content_service.db_add_artifact_to_collection")
@patch("services.authority_content_service.db_create_artifact")
@patch("services.authority_content_service.db_create_collection")
@patch("services.authority_content_service.db_get_artifact", return_value=None)
@patch("services.authority_content_service.db_get_artifact_by_collection_and_root", return_value=None)
@patch("services.authority_content_service.db_get_collection_by_id", return_value=None)
def test_ensure_current_instance_authority_creates_collection_and_artifact(
    _mock_get_collection,
    _mock_get_linked,
    _mock_get_artifact,
    mock_create_collection,
    mock_create_artifact,
    mock_add_artifact,
    _mock_ensure_descriptor,
):
    _setup_registry()
    result = svc.ensure_current_instance_authority(MagicMock())

    # Result is a UUID, not a readable string
    assert result is not None
    uuid.UUID(result)  # validates it's a proper UUID
    assert mock_create_collection.called
    assert mock_create_artifact.called
    mock_add_artifact.assert_called_once()


@patch("services.authority_content_service.db_add_artifact_to_collection")
@patch("services.authority_content_service.db_create_artifact")
@patch("services.authority_content_service.db_create_collection")
@patch("services.authority_content_service.db_get_artifact_by_collection_and_root", return_value=object())
@patch("services.authority_content_service.db_get_collection_by_id")
def test_ensure_current_instance_authority_is_noop_when_link_exists(
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

    result = svc.ensure_current_instance_authority(MagicMock())

    assert result == existing_col.id
    mock_create_collection.assert_not_called()
    mock_create_artifact.assert_not_called()
    mock_add_artifact.assert_not_called()


def test_build_current_instance_authority_context_contains_authority_metadata():
    _setup_registry()
    context = json.loads(svc._build_current_instance_authority_context())

    assert context["type"] == "authority"
    assert context["content_type"] == svc.AUTHORITY_CONTENT_TYPE
    from core import config
    assert context["authority"]["issuer"] == config.AUTHORITY_ISSUER
    # The host artifact ID should be a UUID, not a readable string
    host_id = context["authority"]["current_host_artifact_id"]
    uuid.UUID(host_id)  # validates UUID format


@patch("services.authority_content_service.db_upsert_user_collection_grant")
def test_grant_authority_collection_to_user_upserts_read_grant(mock_upsert):
    mock_upsert.return_value = (MagicMock(), True)
    _setup_registry()
    svc.grant_authority_collection_to_user(MagicMock(), "user-123")

    mock_upsert.assert_called_once()
    kwargs = mock_upsert.call_args.kwargs
    # collection_id should be a UUID resolved from the registry
    uuid.UUID(kwargs["collection_id"])
    assert kwargs["can_read"] is True
    assert kwargs["can_update"] is False
