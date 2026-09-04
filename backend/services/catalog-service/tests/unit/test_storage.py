from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import ClientError

from infrastructure.storage import S3Storage


@asynccontextmanager
async def _client_cm(mock_client: AsyncMock) -> Any:
    yield mock_client


def _storage_with_client(mock_client: AsyncMock) -> S3Storage:
    storage = S3Storage(
        endpoint_url="http://minio:9000",
        public_endpoint_url="http://localhost:9000",
        access_key="key",
        secret_key="secret",
    )
    storage.client = lambda **_kwargs: _client_cm(mock_client)  # type: ignore[method-assign]
    return storage


def _not_found_error(code: str = "404") -> ClientError:
    return ClientError({"Error": {"Code": code}}, "DeleteObject")


@pytest.mark.asyncio
async def test_put_object_overwrites_without_checking_for_existing_object() -> None:
    mock_client = AsyncMock()
    storage = _storage_with_client(mock_client)

    await storage.put_object(
        "product-images", "products/1/image", b"bytes", "image/png"
    )

    mock_client.head_object.assert_not_awaited()
    mock_client.put_object.assert_awaited_once_with(
        Bucket="product-images",
        Key="products/1/image",
        Body=b"bytes",
        ContentType="image/png",
    )


@pytest.mark.asyncio
async def test_delete_object_ignores_missing_object() -> None:
    mock_client = AsyncMock()
    mock_client.delete_object.side_effect = _not_found_error()
    storage = _storage_with_client(mock_client)

    await storage.delete_object("product-images", "products/1/image")

    mock_client.delete_object.assert_awaited_once_with(
        Bucket="product-images", Key="products/1/image"
    )


@pytest.mark.asyncio
async def test_build_presigned_url_requests_a_time_limited_get_url() -> None:
    mock_client = AsyncMock()
    mock_client.generate_presigned_url.return_value = (
        "http://localhost:9000/product-images/products/1/image?X-Amz-Signature=fake"
    )
    storage = _storage_with_client(mock_client)

    result = await storage.build_presigned_url(
        "product-images", "products/1/image", expires_in=600
    )

    assert "X-Amz-Signature=fake" in result
    mock_client.generate_presigned_url.assert_awaited_once_with(
        "get_object",
        Params={"Bucket": "product-images", "Key": "products/1/image"},
        ExpiresIn=600,
    )
