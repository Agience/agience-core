"""Tests for the unified indexing pipeline (post-OpenSearch retirement).

After Step 2.6.9 part 2 the pipeline writes to MANTLE vector cells +
MANTLE-SSE posting lists. The OpenSearch BM25 path and its
``_prepare_base_doc`` shape are gone.

These tests target the surviving public surface:

- ``_extract_artifact_fields`` produces the long-form per-field text
  dict the SSE indexer wants.
- ``index_artifact`` calls the SSE + MANTLE hooks for a non-archived
  artifact and skips archived ones.
- ``index_artifacts_batch`` aggregates across the list.
- ``delete_artifact_from_index`` calls both arms when ``principal_id`` /
  ``collection_id`` are supplied.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch


def _archived_artifact():
    return SimpleNamespace(
        id="art-arch",
        root_id="art-arch",
        state="archived",
        created_by="user-1",
        modified_by="user-1",
        context="{}",
        content="",
        created_time="2026-05-09T00:00:00Z",
    )


def _committed_artifact(*, content="hello world"):
    return SimpleNamespace(
        id="art-1",
        root_id="art-1",
        state="committed",
        created_by="user-1",
        modified_by="user-1",
        collection_id="ws-1",
        context='{"title": "Encryption Library", "description": "A test", "tags": ["test"]}',
        content=content,
        content_type="text/plain",
        name="",
        description="",
        created_time="2026-05-09T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# _extract_artifact_fields
# ---------------------------------------------------------------------------


class TestExtractArtifactFields:
    def test_extracts_title_description_tags_content(self):
        from search.ingest import pipeline_unified

        artifact = _committed_artifact()
        with patch.object(
            pipeline_unified, "extract_text_from_artifact",
            return_value="hello world",
        ):
            fields = pipeline_unified._extract_artifact_fields(artifact)
        assert fields["title"] == "Encryption Library"
        assert fields["description"] == "A test"
        assert fields["tags"] == "test"
        assert fields["content"] == "hello world"

    def test_falls_back_to_artifact_name_for_containers(self):
        from search.ingest import pipeline_unified

        artifact = SimpleNamespace(
            id="ws-1",
            root_id="ws-1",
            state="draft",
            created_by="user-1",
            collection_id="ws-1",
            context="",
            content="",
            name="Untitled Workspace",
            description="Workspace for quick notes",
            content_type="application/vnd.agience.workspace+json",
            created_time="2026-05-09T00:00:00Z",
        )
        with patch.object(
            pipeline_unified, "extract_text_from_artifact", return_value="",
        ):
            fields = pipeline_unified._extract_artifact_fields(artifact)
        assert fields.get("title") == "Untitled Workspace"
        assert fields.get("description") == "Workspace for quick notes"

    def test_invalid_context_json_handled(self):
        from search.ingest import pipeline_unified

        artifact = _committed_artifact()
        artifact.context = "{not json"
        with patch.object(
            pipeline_unified, "extract_text_from_artifact", return_value="x",
        ):
            fields = pipeline_unified._extract_artifact_fields(artifact)
        # No title / description / tags survive a bad context, but content
        # still comes through extract_text_from_artifact.
        assert "content" in fields
        assert "title" not in fields

    def test_empty_artifact_yields_empty_dict(self):
        from search.ingest import pipeline_unified

        artifact = SimpleNamespace(
            id="art-empty",
            root_id="art-empty",
            state="draft",
            created_by="user-1",
            collection_id="ws-1",
            context="{}",
            content="",
            name="",
            description="",
            content_type="text/plain",
            created_time="2026-05-09T00:00:00Z",
        )
        with patch.object(
            pipeline_unified, "extract_text_from_artifact", return_value="",
        ):
            fields = pipeline_unified._extract_artifact_fields(artifact)
        assert fields == {}


# ---------------------------------------------------------------------------
# index_artifact / index_artifacts_batch
# ---------------------------------------------------------------------------


class TestIndexArtifact:
    def test_skips_archived_artifact(self):
        from search.ingest import pipeline_unified

        with (
            patch.object(pipeline_unified, "_sse_index_artifact") as sse,
            patch.object(pipeline_unified, "_mantle_index_artifact") as vec_mock,
        ):
            ok = pipeline_unified.index_artifact(_archived_artifact(), "ws-1")
        assert ok is False
        sse.assert_not_called()
        vec_mock.assert_not_called()

    def test_skips_artifact_with_no_fields(self):
        from search.ingest import pipeline_unified

        artifact = _committed_artifact()
        with (
            patch.object(
                pipeline_unified, "_extract_artifact_fields", return_value={},
            ),
            patch.object(pipeline_unified, "_sse_index_artifact") as sse,
            patch.object(pipeline_unified, "_mantle_index_artifact") as vec_mock,
        ):
            ok = pipeline_unified.index_artifact(artifact, "ws-1")
        assert ok is False
        sse.assert_not_called()
        vec_mock.assert_not_called()

    def test_calls_both_arms_for_committed_artifact(self):
        from search.ingest import pipeline_unified

        artifact = _committed_artifact()
        with (
            patch.object(pipeline_unified, "_sse_index_artifact") as sse,
            patch.object(pipeline_unified, "_mantle_index_artifact") as vec_mock,
            patch.object(
                pipeline_unified, "extract_text_from_artifact",
                return_value="hello world",
            ),
        ):
            ok = pipeline_unified.index_artifact(artifact, "ws-1")
        assert ok is True
        sse.assert_called_once()
        vec_mock.assert_called_once()
        # Both arms get the same fields dict.
        assert sse.call_args[0][2] == vec_mock.call_args[0][2]


class TestIndexArtifactsBatch:
    def test_iterates_and_skips_archived(self):
        from search.ingest import pipeline_unified

        committed = _committed_artifact()
        archived = _archived_artifact()
        with (
            patch.object(pipeline_unified, "_sse_index_artifact") as sse,
            patch.object(pipeline_unified, "_mantle_index_artifact") as vec_mock,
            patch.object(
                pipeline_unified, "extract_text_from_artifact",
                return_value="hello world",
            ),
        ):
            ok = pipeline_unified.index_artifacts_batch(
                [committed, archived], "ws-1",
            )
        assert ok is True
        # Only the committed artifact got indexed.
        assert sse.call_count == 1
        assert vec_mock.call_count == 1


class TestDeleteArtifact:
    def test_calls_both_arms_with_owner_and_collection(self):
        from search.ingest import pipeline_unified

        with (
            patch.object(pipeline_unified, "_mantle_remove_artifact") as vec_mock,
            patch.object(pipeline_unified, "_sse_remove_artifact") as sse,
        ):
            ok = pipeline_unified.delete_artifact_from_index(
                "v-1", root_id="art-1",
                principal_id="user-1", collection_id="ws-1",
            )
        assert ok is True
        vec_mock.assert_called_once_with("user-1", "ws-1", "art-1")
        sse.assert_called_once_with("user-1", "art-1")

    def test_no_owner_skips_both_arms(self):
        from search.ingest import pipeline_unified

        with (
            patch.object(pipeline_unified, "_mantle_remove_artifact") as vec_mock,
            patch.object(pipeline_unified, "_sse_remove_artifact") as sse,
        ):
            ok = pipeline_unified.delete_artifact_from_index("v-1")
        assert ok is True
        vec_mock.assert_not_called()
        sse.assert_not_called()
