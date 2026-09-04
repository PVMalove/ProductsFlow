import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.settings import settings
from infrastructure import storage as storage_module


def test_app_starts_without_invoking_minio_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Достаточно синтаксически валидного URL — create_async_engine() не
    # подключается сразу, но парсить его обязана (прецедент: identity-service's
    # tests/unit/test_main.py). Настоящий settings.catalog_database_url
    # заполняется только через env/.env, поэтому нельзя полагаться на
    # окружение по умолчанию — пустой дефолт поднимет ArgumentError раньше,
    # чем lifespan вообще дойдёт до проверки MinIO, которую доказывает этот тест.
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
