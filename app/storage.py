import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

import aioboto3
from botocore.exceptions import ClientError

from app.settings import settings

if TYPE_CHECKING:
    from types_aiobotocore_s3.client import S3Client

logger = logging.getLogger(__name__)


class S3Storage:
    def __init__(self, endpoint_url: str, access_key: str, secret_key: str) -> None:
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._session: aioboto3.Session = aioboto3.Session()

    @asynccontextmanager
    async def client(self) -> AsyncGenerator["S3Client", None]:
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        ) as client:
            yield cast("S3Client", client)

    async def ensure_bucket_exists(self, bucket_name: str) -> None:
        async with self.client() as client:
            try:
                await client.head_bucket(Bucket=bucket_name)
                logger.debug("Бакет '%s' уже существует.", bucket_name)
            except ClientError as error:
                error_code = error.response.get("Error", {}).get("Code", "")
                if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                    logger.error(
                        "Неожиданная ошибка при проверке бакета '%s': %s",
                        bucket_name,
                        error_code,
                    )
                    raise
                logger.info("Бакет '%s' не найден. Создаём...", bucket_name)
                await client.create_bucket(Bucket=bucket_name)
                logger.info("Бакет '%s' успешно создан.", bucket_name)


def get_storage() -> S3Storage:
    return S3Storage(
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
    )


async def ensure_minio_buckets() -> None:
    storage: S3Storage = get_storage()
    for bucket_name in settings.minio_bucket_names:
        await storage.ensure_bucket_exists(bucket_name)
