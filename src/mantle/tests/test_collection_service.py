from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import collection_service as svc


@patch("services.collection_service.db_get_artifact_by_collection_id_and_root_id")
@patch("services.collection_service.db_get_active_collection_ids_for_user", return_value=["granted-col"])
@patch("services.collection_service.db_get_collections_by_owner_id", return_value=[])
def test_get_collection_cards_batch_global_includes_grant_accessible_collections(
    _mock_owned,
    _mock_grants,
    mock_get_artifact,
):
    expected = SimpleNamespace(root_id="host-root", id="host-version", is_archived=False)

    def side_effect(_db, collection_id, root_id):
        if collection_id == "granted-col" and root_id == "host-root":
            return expected
        return None

    mock_get_artifact.side_effect = side_effect

    artifacts = svc.get_collection_artifacts_batch_global(MagicMock(), "user-1", ["host-root"])

    assert artifacts == [expected]
    mock_get_artifact.assert_any_call(AnyDbMatcher(), "granted-col", "host-root")


class AnyDbMatcher:
    def __eq__(self, other):
        return True