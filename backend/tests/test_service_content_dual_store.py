import io

from services import content_service as content


class FakeS3Client:
    def __init__(self, *, presign_base: str = "https://edge.example", objects=None):
        self.presign_base = presign_base
        self.objects = dict(objects or {})
        self.deleted = []

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Exception("missing")
        item = self.objects[Key]
        return {
            "ContentLength": len(item.get("Body", b"")),
            "ContentType": item.get("ContentType"),
            "CacheControl": item.get("CacheControl"),
        }

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Exception("missing")
        item = self.objects[Key]
        return {
            "Body": io.BytesIO(item.get("Body", b"")),
            "ContentType": item.get("ContentType"),
            "CacheControl": item.get("CacheControl"),
        }

    def put_object(self, Bucket, Key, Body, ContentType=None, CacheControl=None):
        data = Body.read() if hasattr(Body, "read") else Body
        self.objects[Key] = {
            "Body": data,
            "ContentType": ContentType,
            "CacheControl": CacheControl,
        }
        return {"ETag": "etag"}

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key, None)
        return {}

    def generate_presigned_url(self, operation_name, Params, ExpiresIn):
        return f"{self.presign_base}/{Params['Bucket']}/{Params['Key']}?op={operation_name}"

    def create_bucket(self, **kwargs):
        return {}


def test_persist_object_to_durable_and_evict_edge(monkeypatch):
    key = "tenant/artifact.content"
    edge_internal = FakeS3Client(
        objects={
            key: {
                "Body": b"hello",
                "ContentType": "text/plain",
                "CacheControl": "private, max-age=31536000, immutable",
            }
        }
    )
    durable = FakeS3Client()

    monkeypatch.setattr(content, "_s3_edge_internal", edge_internal)
    monkeypatch.setattr(content, "_s3_durable", durable)
    monkeypatch.setattr(content, "_EDGE_BUCKET", "edge-bucket")
    monkeypatch.setattr(content, "_DURABLE_BUCKET", "durable-bucket")
    monkeypatch.setattr(content, "_EVICT_EDGE_AFTER_DURABLE_SYNC", True)

    assert content.persist_object_to_durable(key) is True
    assert key in durable.objects
    assert key not in edge_internal.objects
    assert edge_internal.deleted == [key]


def test_generate_signed_url_hydrates_edge_from_durable(monkeypatch):
    key = "tenant/artifact.content"
    edge_internal = FakeS3Client()
    edge_public = FakeS3Client(presign_base="https://minio.example")
    durable = FakeS3Client(
        objects={
            key: {
                "Body": b"hello",
                "ContentType": "text/plain",
                "CacheControl": "private, max-age=31536000, immutable",
            }
        }
    )

    monkeypatch.setattr(content, "_s3_edge_internal", edge_internal)
    monkeypatch.setattr(content, "_s3_edge_public", edge_public)
    monkeypatch.setattr(content, "_s3_durable", durable)
    monkeypatch.setattr(content, "_EDGE_BUCKET", "edge-bucket")
    monkeypatch.setattr(content, "_DURABLE_BUCKET", "durable-bucket")
    monkeypatch.setattr(content, "_BUCKET_CHECKED", True)

    url = content.generate_signed_url(key, filename="a.txt", content_type="text/plain")

    assert url.startswith("https://minio.example/edge-bucket/tenant/artifact.content")
    assert key in edge_internal.objects


def test_get_content_storage_mode_minio_only(monkeypatch):
    monkeypatch.setattr(content, "_s3_durable", None)
    monkeypatch.setattr(content, "_DURABLE_BUCKET", "")
    monkeypatch.delenv("CLOUDFRONT_KEY_ID", raising=False)
    monkeypatch.delenv("CLOUDFRONT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("CLOUDFRONT_PRIVATE_KEY_PATH", raising=False)

    assert content.get_content_storage_mode() == "minio-only"


def test_get_content_storage_mode_minio_s3_backed(monkeypatch):
    monkeypatch.setattr(content, "_s3_durable", object())
    monkeypatch.setattr(content, "_DURABLE_BUCKET", "durable-bucket")
    monkeypatch.delenv("CLOUDFRONT_KEY_ID", raising=False)
    monkeypatch.delenv("CLOUDFRONT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("CLOUDFRONT_PRIVATE_KEY_PATH", raising=False)

    assert content.get_content_storage_mode() == "minio-s3-backed"


def test_get_content_storage_mode_cloudfront_s3(monkeypatch):
    monkeypatch.setattr(content, "_s3_durable", object())
    monkeypatch.setattr(content, "_DURABLE_BUCKET", "durable-bucket")
    monkeypatch.setenv("CLOUDFRONT_KEY_ID", "key-id")
    monkeypatch.setenv("CLOUDFRONT_PRIVATE_KEY_PATH", "private.pem")
    monkeypatch.delenv("CLOUDFRONT_PRIVATE_KEY", raising=False)

    assert content.get_content_storage_mode() == "cloudfront-s3"
