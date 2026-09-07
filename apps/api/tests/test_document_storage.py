from types import SimpleNamespace
from typing import cast

import pytest
from app.documents.storage import MinioObjectStorage
from minio import Minio
from minio.error import S3Error
from minio.versioningconfig import VersioningConfig


class RacingBucketClient:
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        self.versioning = VersioningConfig()

    def get_bucket_versioning(self, bucket: str) -> VersioningConfig:
        assert bucket == "documents"
        return self.versioning

    def set_bucket_versioning(self, bucket: str, config: VersioningConfig) -> None:
        assert bucket == "documents"
        self.versioning = config

    def bucket_exists(self, bucket: str) -> bool:
        assert bucket == "documents"
        return False

    def make_bucket(self, bucket: str) -> None:
        assert bucket == "documents"
        raise S3Error(None, self.error_code, "race", bucket, "request", "host")


def storage_with(client: RacingBucketClient) -> MinioObjectStorage:
    storage = object.__new__(MinioObjectStorage)
    storage._bucket = "documents"
    storage._client = cast(Minio, client)
    return storage


@pytest.mark.parametrize("error_code", ["BucketAlreadyExists", "BucketAlreadyOwnedByYou"])
def test_bucket_creation_tolerates_a_concurrent_creator(error_code: str) -> None:
    client = RacingBucketClient(error_code)
    storage_with(client).ensure_bucket()
    assert client.versioning.status == "Enabled"


def test_bucket_creation_preserves_unexpected_storage_errors() -> None:
    with pytest.raises(S3Error, match="AccessDenied"):
        storage_with(RacingBucketClient("AccessDenied")).ensure_bucket()


@pytest.mark.parametrize("version_id", [None, "null"])
def test_inspection_rejects_mutable_unversioned_objects(version_id):
    class UnversionedClient:
        def stat_object(self, *args, **kwargs):
            return SimpleNamespace(size=5, version_id=version_id)

        def get_object(self, *args, **kwargs):
            raise AssertionError("Unversioned content must not be downloaded or trusted")

    storage = object.__new__(MinioObjectStorage)
    storage._bucket = "documents"
    storage._client = cast(Minio, UnversionedClient())
    with pytest.raises(ValueError, match="versioning must be enabled"):
        storage.inspect("organization/document/version")
