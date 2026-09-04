from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Дефолт резолвится относительно расположения этого файла на диске
# (стабильно независимо от CWD процесса — `make test`/`make dev` запускают
# pytest/uvicorn из `backend/`, не из директории самого этого пакета).
# Переопределяется абсолютным путём в образе контейнера, где этот модуль
# установлен в `.venv/site-packages` (Dockerfile копирует assets/ в
# /srv/assets).
_DEFAULT_SEED_PLACEHOLDER_IMAGE_PATH = str(
    Path(__file__).resolve().parents[2] / "assets" / "placeholder.jpg"
)


class Settings(BaseSettings):
    app_env: str = "dev"
    catalog_database_url: str = ""
    catalog_amqp_url: str = "amqp://guest:guest@localhost:5672/"
    # Базовый URL identity-service для `IdentityClient` (JWKS-верификация,
    # `GET /api/v1/users/me`, ADR 0005/0011) — имя сервиса compose-сети
    # (`backend/docker-compose.yml`), не публичный хост.
    catalog_identity_base_url: str = "http://identity-api:8000"
    minio_endpoint: str = "http://minio:9000"
    minio_public_endpoint: str = "http://localhost:9002"
    minio_root_user: str = "minio-admin"
    minio_root_password: str = "minio-secret-key"
    minio_bucket_name_product: str = "product-chunks"
    minio_bucket_name_loki: str = "loki-chunks"
    minio_bucket_name_tempo: str = "tempo-traces"
    catalog_seed_placeholder_image_path: str = _DEFAULT_SEED_PLACEHOLDER_IMAGE_PATH

    @property
    def minio_bucket_names(self) -> tuple[str, ...]:
        return (
            self.minio_bucket_name_product,
            self.minio_bucket_name_loki,
            self.minio_bucket_name_tempo,
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
