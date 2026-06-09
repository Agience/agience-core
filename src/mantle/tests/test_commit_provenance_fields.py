from unittest.mock import patch

from entities.commit import Commit
from services.collection_service import record_collection_commit


class _DummyDb:
    pass


def test_commit_entity_round_trip_includes_provenance_fields():
    commit = Commit(
        id="cm-1",
        message="msg",
        author_id="user-1",
        confirmation="human_affirmed",
        changeset_type="automation",
        item_ids=["it-1"],
    )

    payload = commit.to_dict()
    assert payload["confirmation"] == "human_affirmed"
    assert payload["changeset_type"] == "automation"

    restored = Commit.from_dict(payload)
    assert restored.confirmation == "human_affirmed"
    assert restored.changeset_type == "automation"


@patch("services.collection_service.db_create_commit", autospec=True)
@patch("services.collection_service.db_create_commit_items", autospec=True, return_value=[])
def test_record_collection_commit_defaults_provenance_fields(
    _mock_create_items,
    mock_create_commit,
):
    db = _DummyDb()

    record_collection_commit(
        db,
        user_id="user-1",
        collection_id="col-1",
        adds=["v-1"],
    )

    created_commit = mock_create_commit.call_args[0][1]
    assert created_commit.confirmation == "human_affirmed"
    assert created_commit.changeset_type == "manual"


@patch("services.collection_service.db_create_commit", autospec=True)
@patch("services.collection_service.db_create_commit_items", autospec=True, return_value=[])
def test_record_collection_commit_accepts_explicit_provenance_fields(
    _mock_create_items,
    mock_create_commit,
):
    db = _DummyDb()

    record_collection_commit(
        db,
        user_id="user-1",
        collection_id="col-1",
        adds=["v-1"],
        confirmation="human_affirmed",
        changeset_type="automation",
    )

    created_commit = mock_create_commit.call_args[0][1]
    assert created_commit.confirmation == "human_affirmed"
    assert created_commit.changeset_type == "automation"
