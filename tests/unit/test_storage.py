import json
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from botocore.exceptions import ClientError

from app import storage as storage_module
from app.settings import settings
from app.storage import S3Storage, ensure_minio_buckets, get_storage


@asynccontextmanager # type: ignore
async def _client_cm(mock_client: AsyncMock) -> Any:
    yield mock_client


def _storage_with_client(mock_client: AsyncMock) -> S3Storage:
    storage = S3Storage(
        endpoint_url="http://minio:9000", access_key="key", secret_key="secret"
    )
    storage.client = lambda: _client_cm(mock_client)  # type: ignore[method-assign]
    return storage


def _not_found_error(code: str = "404") -> ClientError:
    return ClientError({"Error": {"Code": code}}, "HeadBucket")


async def test_ensure_bucket_exists_creates_bucket_when_missing():
    mock_client = AsyncMock()
    mock_client.head_bucket.side_effect = _not_found_error()
    storage = _storage_with_client(mock_client)

    await storage.ensure_bucket_exists("product-chunks")

    mock_client.create_bucket.assert_awaited_once_with(Bucket="product-chunks")


async def test_ensure_bucket_exists_skips_creation_when_bucket_present():
    mock_client = AsyncMock()
    storage = _storage_with_client(mock_client)

    await storage.ensure_bucket_exists("product-chunks")

    mock_client.head_bucket.assert_awaited_once_with(Bucket="product-chunks")
    mock_client.create_bucket.assert_not_awaited()


async def test_ensure_bucket_exists_reraises_unexpected_client_error():
    mock_client = AsyncMock()
    mock_client.head_bucket.side_effect = _not_found_error(code="403")
    storage = _storage_with_client(mock_client)

    with pytest.raises(ClientError):
        await storage.ensure_bucket_exists("product-chunks")

    mock_client.create_bucket.assert_not_awaited()


async def test_set_public_read_policy_grants_public_get_object():
    mock_client = AsyncMock()
    storage = _storage_with_client(mock_client)

    await storage.set_public_read_policy("product-chunks")

    mock_client.put_bucket_policy.assert_awaited_once()
    _, kwargs = mock_client.put_bucket_policy.call_args
    assert kwargs["Bucket"] == "product-chunks"
    assert json.loads(kwargs["Policy"]) == {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::product-chunks/*",
            }
        ],
    }


def test_get_storage_builds_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "minio_endpoint", "http://minio:9000")
    monkeypatch.setattr(settings, "minio_root_user", "root-user")
    monkeypatch.setattr(settings, "minio_root_password", "root-pass")

    storage = get_storage()

    assert storage._endpoint_url == "http://minio:9000"
    assert storage._access_key == "root-user"
    assert storage._secret_key == "root-pass"


async def test_ensure_minio_buckets_creates_all_and_grants_public_read_to_product(
    monkeypatch,
):
    monkeypatch.setattr(settings, "minio_bucket_name_product", "product-chunks")
    monkeypatch.setattr(settings, "minio_bucket_name_loki", "loki-chunks")
    monkeypatch.setattr(settings, "minio_bucket_name_tempo", "tempo-traces")

    fake_storage = MagicMock()
    fake_storage.ensure_bucket_exists = AsyncMock()
    fake_storage.set_public_read_policy = AsyncMock()
    monkeypatch.setattr(storage_module, "get_storage", lambda: fake_storage)

    await ensure_minio_buckets()

    assert fake_storage.ensure_bucket_exists.await_args_list == [
        call("product-chunks"),
        call("loki-chunks"),
        call("tempo-traces"),
    ]
    fake_storage.set_public_read_policy.assert_awaited_once_with("product-chunks")
