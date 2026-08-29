from pathlib import Path

import pytest
from identity_service.settings import Settings


def test_settings_defaults_are_safe_for_a_fresh_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # cwd без .env и без унаследованных переменных — дефолты должны прочитаться
    # как есть, а не подхватить локальный backend/.env разработчика.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("IDENTITY_JWT_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.delenv("IDENTITY_ACCESS_TOKEN_TTL_HOURS", raising=False)

    settings = Settings()

    assert settings.app_env == "dev"
    assert settings.identity_jwt_private_key_path == ""
    assert settings.identity_access_token_ttl_hours == 1
