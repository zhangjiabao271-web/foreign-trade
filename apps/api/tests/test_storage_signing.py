from datetime import timedelta
from urllib.parse import urlparse

from app.core.config import Settings
from app.documents.storage import MinioObjectStorage
from urllib3 import PoolManager


def test_public_signer_uses_browser_endpoint_without_network(monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("Presigning must not access the network")

    monkeypatch.setattr(PoolManager, "urlopen", reject_network)
    storage = MinioObjectStorage(
        Settings(
            minio_host="minio",
            minio_public_endpoint="files.example.test:9443",
            minio_public_secure=True,
            minio_region="us-east-1",
        )
    )
    for url in (
        storage.presign_upload("org/document/version", expires=timedelta(minutes=15)),
        storage.presign_download(
            "org/document/version", expires=timedelta(minutes=5), version_id="pinned-v1"
        ),
    ):
        parsed = urlparse(url)
        assert parsed.netloc == "files.example.test:9443"
        assert parsed.scheme == "https"
        assert "X-Amz-Signature=" in parsed.query
