from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Default resolves against this file's on-disk location (stable regardless
# of the process's CWD — `make test`/`make dev` run pytest/uvicorn from
# `backend/`, not from this package's own directory). Overridden by an
# absolute path in the container image, where this module is installed into
# `.venv/site-packages` instead (Dockerfile copies assets/ to /srv/assets).
_DEFAULT_SEED_PLACEHOLDER_IMAGE_PATH = str(
    Path(__file__).resolve().parents[2] / "assets" / "placeholder.jpg"
)


class Settings(BaseSettings):
    app_env: str = "dev"
    catalog_database_url: str = ""
    catalog_amqp_url: str = "amqp://guest:guest@localhost:5672/"
    # Базовый URL identity-service для `IdentityClient` (JWKS-верификация,
    # `GET /api/v1/users/me`, ADR 0011/0012) — имя сервиса compose-сети
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
