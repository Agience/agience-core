from types import SimpleNamespace
from unittest.mock import patch


def test_index_workspace_artifact_uses_extracted_text_for_s3_backed_content():
    from search.ingest import pipeline_unified

    artifact = SimpleNamespace(
        id="art-1",
        root_id=None,
        created_by="user-1",
        modified_by="user-1",
        collection_id="ws-1",
        state="new",
        context='{"content_type":"text/plain","content_key":"tenant/art-1.content"}',
        content="",
        created_time="2026-03-21T00:00:00Z",
    )

    with patch.object(pipeline_unified, "extract_text_from_artifact", return_value="s3 text body") as mock_extract, \
         patch.object(pipeline_unified, "bulk_index_documents") as mock_bulk_index, \
         patch.object(pipeline_unified, "_embeddings", return_value=[[0.1, 0.2, 0.3]]):
        ok = pipeline_unified.index_artifact(artifact, "ws-1")

    assert ok is True
    mock_extract.assert_called_once_with(artifact)

    chunk_records = mock_bulk_index.call_args[0][1]
    assert chunk_records[0]["content"] == "s3 text body"


def test_index_container_artifact_uses_name_description_when_context_empty():
    from search.ingest import pipeline_unified

    artifact = SimpleNamespace(
        id="ws-1",
        root_id="ws-1",
        created_by="user-1",
        modified_by="user-1",
        collection_id="ws-1",
        state="draft",
        context="",
        content="",
        name="Untitled Workspace",
        description="Workspace for quick notes",
        content_type="application/vnd.agience.workspace+json",
        created_time="2026-04-11T00:00:00Z",
    )

    with patch.object(pipeline_unified, "extract_text_from_artifact", return_value="") as mock_extract, \
         patch.object(pipeline_unified, "bulk_index_documents") as mock_bulk_index, \
         patch.object(pipeline_unified, "_embeddings", return_value=[[0.1, 0.2, 0.3]]):
        ok = pipeline_unified.index_artifact(artifact, "ws-1")

    assert ok is True
    mock_extract.assert_called_once_with(artifact)

    chunk_records = mock_bulk_index.call_args[0][1]
    assert chunk_records[0]["title"] == "Untitled Workspace"
    assert chunk_records[0]["description"] == "Workspace for quick notes"
    assert chunk_records[0]["metadata"]["content_type"] == "application/vnd.agience.workspace+json"
    assert "Untitled Workspace" in chunk_records[0]["content"]