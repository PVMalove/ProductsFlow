from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    catalog_database_url: str = ""
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

    @property
    def minio_bucket_names(self) -> tuple[str, ...]:
        return (
            self.minio_bucket_name_product,
            self.minio_bucket_name_loki,
            self.minio_bucket_name_tempo,
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
