import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.settings import settings


def test_app_startup_fails_fast_in_prod_without_a_configured_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "identity_jwt_private_key_path", "")

    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_app_starts_in_dev_without_a_configured_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "identity_jwt_private_key_path", "")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/.well-known/jwks.json")

    # Стартует без ошибки; сам JWKS без настроенного ключа не отдаётся — 500,
    # а не крах старта (AC покрывает только APP_ENV=prod).
    assert response.status_code == 500
