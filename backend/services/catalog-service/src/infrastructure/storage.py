import inspect
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import aioboto3
from botocore.exceptions import ClientError
from fastapi import Depends

from core.settings import settings

logger = logging.getLogger(__name__)


class S3Storage:
    """S3-compatible object storage adapter for catalog images."""

    def __init__(
        self,
        endpoint_url: str,
        public_endpoint_url: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._public_endpoint_url = public_endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._session = aioboto3.Session()

    @asynccontextmanager
    async def client(
        self, *, endpoint_url: str | None = None
    ) -> AsyncGenerator[Any, None]:
        async with self._session.client(
            "s3",
            endpoint_url=endpoint_url or self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        ) as client:
            yield client

    async def put_object(
        self, bucket_name: str, key: str, body: bytes, content_type: str
    ) -> None:
        """Write an object unconditionally, replacing an existing object."""
        async with self.client() as client:
            await client.put_object(
                Bucket=bucket_name,
                Key=key,
                Body=body,
                ContentType=content_type,
            )

    async def delete_object(self, bucket_name: str, key: str) -> None:
        """Delete an object and tolerate it already being absent."""
        async with self.client() as client:
            try:
                await client.delete_object(Bucket=bucket_name, Key=key)
            except ClientError as error:
                error_code = error.response.get("Error", {}).get("Code", "")
                if error_code not in {"404", "NoSuchKey", "NotFound"}:
                    raise

    async def ensure_bucket_exists(self, bucket_name: str) -> None:
        async with self.client() as client:
            try:
                await client.head_bucket(Bucket=bucket_name)
            except ClientError as error:
                error_code = error.response.get("Error", {}).get("Code", "")
                if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                    raise
                await client.create_bucket(Bucket=bucket_name)

    async def build_presigned_url(
        self, bucket_name: str, key: str, expires_in: int = 3600
    ) -> str:
        """Build a time-limited read URL without making the bucket public."""
        async with self.client(endpoint_url=self._public_endpoint_url) as client:
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            if inspect.isawaitable(url):
                url = await url
            return str(url)


def get_storage() -> S3Storage:
    return S3Storage(
        endpoint_url=settings.minio_endpoint,
        public_endpoint_url=settings.minio_public_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
    )


StorageDI = Annotated[S3Storage, Depends(get_storage)]


async def ensure_minio_buckets() -> None:
    storage = get_storage()
    for bucket_name in settings.minio_bucket_names:
        await storage.ensure_bucket_exists(bucket_name)


__all__ = ["S3Storage", "StorageDI", "ensure_minio_buckets", "get_storage"]
