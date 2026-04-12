"""Unit tests for services.content_service.

The S3-heavy code is intentionally only tested at the boundary; we mock the
boto3 clients (`_s3_edge_internal`, `_s3_edge_public`, `_s3_durable`) and
verify the dispatch decisions. Pure helpers are tested directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services import content_service


# ---------------------------------------------------------------------------
# _env_flag
# ---------------------------------------------------------------------------

class TestEnvFlag:
    def test_truthy_values(self, monkeypatch):
        for v in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("FOO", v)
            assert content_service._env_flag("FOO") is True

    def test_falsy_values(self, monkeypatch):
        for v in ("0", "false", "no", "off", ""):
            monkeypatch.setenv("FOO", v)
            assert content_service._env_flag("FOO") is False

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("FOO", raising=False)
        assert content_service._env_flag("FOO", default=True) is True
        assert content_service._env_flag("FOO", default=False) is False


# ---------------------------------------------------------------------------
# get_content_storage_mode
# ---------------------------------------------------------------------------

class TestGetContentStorageMode:
    def test_minio_only_when_no_durable_no_cloudfront(self, monkeypatch):
        monkeypatch.delenv("CLOUDFRONT_KEY_ID", raising=False)
        monkeypatch.delenv("CLOUDFRONT_PRIVATE_KEY", raising=False)
        with patch("services.content_service._durable_store_enabled", return_value=False):
            assert content_service.get_content_storage_mode() == "minio-only"

    def test_minio_s3_backed_when_durable_only(self, monkeypatch):
        monkeypatch.delenv("CLOUDFRONT_KEY_ID", raising=False)
        with patch(
            "services.content_service._durable_store_enabled", return_value=True
        ):
            assert content_service.get_content_storage_mode() == "minio-s3-backed"

    def test_cloudfront_s3_when_both_configured(self, monkeypatch):
        monkeypatch.setenv("CLOUDFRONT_KEY_ID", "K1")
        monkeypatch.setenv("CLOUDFRONT_PRIVATE_KEY", "----BEGIN----")
        with patch(
            "services.content_service._durable_store_enabled", return_value=True
        ):
            assert content_service.get_content_storage_mode() == "cloudfront-s3"

    def test_cloudfront_without_durable_falls_back_to_minio(self, monkeypatch):
        monkeypatch.setenv("CLOUDFRONT_KEY_ID", "K1")
        monkeypatch.setenv("CLOUDFRONT_PRIVATE_KEY", "----BEGIN----")
        with patch(
            "services.content_service._durable_store_enabled", return_value=False
        ):
            assert content_service.get_content_storage_mode() == "minio-only"


# ---------------------------------------------------------------------------
# build_public_content_url
# ---------------------------------------------------------------------------

class TestBuildPublicContentUrl:
    def test_strips_trailing_slash_from_base(self):
        with patch("core.config.CONTENT_URI", "https://content.example/"):
            url = content_service.build_public_content_url("art-1", "doc.pdf")
        assert url == "https://content.example/files/art-1/doc.pdf"

    def test_replaces_path_separators_in_filename(self):
        with patch("core.config.CONTENT_URI", "https://content.example"):
            url = content_service.build_public_content_url("art-1", "a/b/c.pdf")
        # Forward slashes in the filename are replaced so the path stays
        # predictable; the resulting URL should contain the flattened name
        # and NOT the original slashed form.
        assert "a_b_c.pdf" in url
        assert "/a/b/c.pdf" not in url


# ---------------------------------------------------------------------------
# presign_put_or_multipart
# ---------------------------------------------------------------------------

class TestPresignPutOrMultipart:
    def test_single_put_under_threshold(self):
        with (
            patch("services.content_service._ensure_bucket_exists_once"),
            patch.object(
                content_service._s3_edge_public,
                "generate_presigned_url",
                return_value="https://signed.example/put",
            ),
        ):
            out = content_service.presign_put_or_multipart(
                "u/key.bin", "application/octet-stream", size=1024
            )
        assert out == {"mode": "put", "url": "https://signed.example/put"}

    def test_multipart_over_threshold(self):
        with (
            patch("services.content_service._ensure_bucket_exists_once"),
            patch.object(
                content_service._s3_edge_internal,
                "create_multipart_upload",
                return_value={"UploadId": "mp-9"},
            ),
        ):
            out = content_service.presign_put_or_multipart(
                "u/big.bin",
                "application/octet-stream",
                size=content_service.SINGLE_PUT_MAX + 1,
            )
        assert out == {"mode": "multipart", "uploadId": "mp-9"}


# ---------------------------------------------------------------------------
# generate_multipart_part_url
# ---------------------------------------------------------------------------

class TestGenerateMultipartPartUrl:
    def test_calls_upload_part_with_correct_params(self):
        with (
            patch("services.content_service._ensure_bucket_exists_once"),
            patch.object(
                content_service._s3_edge_public,
                "generate_presigned_url",
                return_value="https://signed.example/part",
            ) as gen,
        ):
            out = content_service.generate_multipart_part_url(
                "u/k.bin", "mp-9", part_number=3
            )
        assert out == "https://signed.example/part"
        kwargs = gen.call_args.kwargs
        assert kwargs["Params"]["UploadId"] == "mp-9"
        assert kwargs["Params"]["PartNumber"] == 3


# ---------------------------------------------------------------------------
# complete_multipart
# ---------------------------------------------------------------------------

class TestCompleteMultipart:
    def test_sorts_parts_before_completing(self):
        with patch.object(
            content_service._s3_edge_internal,
            "complete_multipart_upload",
            return_value={"ETag": "abc"},
        ) as complete:
            content_service.complete_multipart(
                "u/k.bin",
                "mp-9",
                parts=[
                    {"PartNumber": 3, "ETag": "c"},
                    {"PartNumber": 1, "ETag": "a"},
                    {"PartNumber": 2, "ETag": "b"},
                ],
            )
        sent_parts = complete.call_args.kwargs["MultipartUpload"]["Parts"]
        assert [p["PartNumber"] for p in sent_parts] == [1, 2, 3]


# ---------------------------------------------------------------------------
# head_object
# ---------------------------------------------------------------------------

class TestHeadObject:
    def test_returns_metadata_when_present(self):
        with patch.object(
            content_service._s3_edge_internal,
            "head_object",
            return_value={"ContentLength": 1024},
        ):
            assert content_service.head_object("k") == {"ContentLength": 1024}

    def test_returns_none_on_error(self):
        with patch.object(
            content_service._s3_edge_internal,
            "head_object",
            side_effect=Exception("not found"),
        ):
            assert content_service.head_object("k") is None


# ---------------------------------------------------------------------------
# delete_object
# ---------------------------------------------------------------------------

class TestDeleteObject:
    def test_deletes_edge_only_when_durable_disabled(self):
        with (
            patch.object(
                content_service._s3_edge_internal, "delete_object"
            ) as edge_del,
            patch(
                "services.content_service._durable_store_enabled", return_value=False
            ),
        ):
            assert content_service.delete_object("k") is True
        edge_del.assert_called_once()

    def test_deletes_both_when_durable_enabled(self):
        durable = MagicMock()
        with (
            patch.object(
                content_service._s3_edge_internal, "delete_object"
            ) as edge_del,
            patch(
                "services.content_service._durable_store_enabled", return_value=True
            ),
            patch("services.content_service._s3_durable", durable),
        ):
            assert content_service.delete_object("k") is True
        edge_del.assert_called_once()
        durable.delete_object.assert_called_once()

    def test_returns_false_when_both_fail(self):
        with (
            patch.object(
                content_service._s3_edge_internal,
                "delete_object",
                side_effect=Exception("fail"),
            ),
            patch(
                "services.content_service._durable_store_enabled", return_value=False
            ),
        ):
            assert content_service.delete_object("k") is False

    def test_returns_true_when_edge_fails_but_durable_succeeds(self):
        durable = MagicMock()
        with (
            patch.object(
                content_service._s3_edge_internal,
                "delete_object",
                side_effect=Exception("edge fail"),
            ),
            patch(
                "services.content_service._durable_store_enabled", return_value=True
            ),
            patch("services.content_service._s3_durable", durable),
        ):
            assert content_service.delete_object("k") is True
