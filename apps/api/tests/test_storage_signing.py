from datetime import timedelta
from urllib.parse import parse_qs, quote, urlparse

import pytest
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
            "org/document/version",
            expires=timedelta(minutes=5),
            version_id="pinned-v1",
            file_name="SIM-BOL-20260907-A.txt",
        ),
    ):
        parsed = urlparse(url)
        assert parsed.netloc == "files.example.test:9443"
        assert parsed.scheme == "https"
        assert "X-Amz-Signature=" in parsed.query


@pytest.mark.parametrize(
    "file_name", ["SIM-BOL-20260907-A.txt", "提单 甲.pdf", 'a";\r\nX-Test: injected.txt']
)
def test_download_signs_attachment_filename_and_exact_version(file_name):
    storage = MinioObjectStorage(Settings(minio_region="us-east-1"))
    url = storage.presign_download(
        "org/document/random-key",
        expires=timedelta(minutes=5),
        version_id="original-storage-version",
        file_name=file_name,
    )
    query = parse_qs(urlparse(url).query)
    disposition = query["response-content-disposition"][0]
    assert (
        disposition
        == f"attachment; filename=\"download\"; filename*=UTF-8''{quote(file_name, safe='')}"
    )
    assert "\r" not in disposition and "\n" not in disposition
    assert query["versionId"] == ["original-storage-version"]
    assert query["X-Amz-Expires"] == ["300"]
    assert query["X-Amz-Signature"]
