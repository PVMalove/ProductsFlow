import pytest
from fastapi.testclient import TestClient

from api.main import app
from infrastructure import storage as storage_module


def test_app_starts_without_invoking_minio_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_if_constructed(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "S3Storage must not be constructed during catalog-service startup"
        )

    monkeypatch.setattr(storage_module.S3Storage, "__init__", _fail_if_constructed)

    with TestClient(app):
        pass
