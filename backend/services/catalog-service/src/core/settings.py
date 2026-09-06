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
    catalog_opensearch_url: str = "http://localhost:9200"
    catalog_search_index_name: str = "catalog-products"
    catalog_outbox_poll_interval_seconds: float = 5.0
    catalog_redis_url: str = "redis://localhost:6379/0"
    # Ровно 60с (issue #293 acceptance criterion 2) — TTL, не сложная
    # адресная инвалидация, и есть контракт свежести первой страницы поиска.
    catalog_search_cache_ttl_seconds: int = 60
    catalog_search_worker_metrics_port: int = 9100
    catalog_rabbitmq_management_url: str = "http://localhost:15672"
    catalog_rabbitmq_management_user: str = "guest"
    catalog_rabbitmq_management_password: str = "guest"
    catalog_search_dlq_poll_interval_seconds: float = 5.0
    catalog_search_reindex_batch_size: int = 500
    catalog_search_reconcile_throttle_seconds: float = 0.05
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

    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800

    @property
    def minio_bucket_names(self) -> tuple[str, ...]:
        return (
            self.minio_bucket_name_product,
            self.minio_bucket_name_loki,
            self.minio_bucket_name_tempo,
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
