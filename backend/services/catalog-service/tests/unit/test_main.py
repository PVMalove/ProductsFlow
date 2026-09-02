import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.settings import settings
from infrastructure import storage as storage_module


def test_app_starts_without_invoking_minio_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A syntactically valid URL is enough — create_async_engine() doesn't
    # connect eagerly, but it does need to parse (prior art: identity-service's
    # tests/unit/test_main.py). The real settings.catalog_database_url is only
    # populated via env/.env, so this must not be left to the ambient
    # environment — an empty default raises ArgumentError before lifespan
    # ever reaches the MinIO check this test exists to prove.
    monkeypatch.setattr(
        settings,
        "catalog_database_url",
        "postgresql+asyncpg://catalog:catalog@localhost/catalog",
    )

    def _fail_if_constructed(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "S3Storage must not be constructed during catalog-service startup"
        )

    monkeypatch.setattr(storage_module.S3Storage, "__init__", _fail_if_constructed)

    with TestClient(app):
        pass
