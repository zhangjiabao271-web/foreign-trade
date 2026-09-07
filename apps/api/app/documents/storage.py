from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from typing import Protocol

from minio import Minio
from minio.commonconfig import ENABLED
from minio.error import S3Error
from minio.versioningconfig import VersioningConfig

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class StoredObject:
    size: int
    content_type: str | None
    sha256: str
    version_id: str | None = None


class ObjectStorage(Protocol):
    def ensure_bucket(self) -> None: ...

    def presign_upload(self, object_key: str, *, expires: timedelta) -> str: ...

    def presign_download(self, object_key: str, *, expires: timedelta, version_id: str) -> str: ...

    def inspect(self, object_key: str, *, version_id: str | None = None) -> StoredObject: ...


class MinioObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.minio_bucket
        self._client = Minio(
            f"{settings.minio_host}:{settings.minio_port}",
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            region=settings.minio_region,
        )
        self._signer = Minio(
            settings.minio_public_endpoint or f"{settings.minio_host}:{settings.minio_port}",
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_public_secure
            if settings.minio_public_endpoint
            else settings.minio_secure,
            region=settings.minio_region,
        )

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            try:
                self._client.make_bucket(self._bucket)
            except S3Error as error:
                if error.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                    raise
        if self._client.get_bucket_versioning(self._bucket).status != ENABLED:
            self._client.set_bucket_versioning(self._bucket, VersioningConfig(ENABLED))

    def presign_upload(self, object_key: str, *, expires: timedelta) -> str:
        return self._signer.presigned_put_object(self._bucket, object_key, expires=expires)

    def presign_download(self, object_key: str, *, expires: timedelta, version_id: str) -> str:
        return self._signer.presigned_get_object(
            self._bucket, object_key, expires=expires, version_id=version_id
        )

    def inspect(self, object_key: str, *, version_id: str | None = None) -> StoredObject:
        stat = self._client.stat_object(self._bucket, object_key, version_id=version_id)
        if stat.size is None:
            raise ValueError("Object storage did not return a size")
        if not stat.version_id or stat.version_id == "null":
            raise ValueError("Object storage versioning must be enabled before completion")
        response = self._client.get_object(self._bucket, object_key, version_id=stat.version_id)
        digest = sha256()
        try:
            for chunk in response.stream(1024 * 1024):
                digest.update(chunk)
        finally:
            response.close()
            response.release_conn()
        return StoredObject(
            size=stat.size,
            content_type=stat.content_type,
            sha256=digest.hexdigest(),
            version_id=stat.version_id,
        )


def iter_object_bytes(data: bytes, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    for offset in range(0, len(data), chunk_size):
        yield data[offset : offset + chunk_size]
