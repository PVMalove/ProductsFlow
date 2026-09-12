from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    payment_database_url: str = ""
    # Базовый URL identity-service для `IdentityClient` (JWKS-верификация,
    # ADR 0005/0011) — имя сервиса compose-сети (`backend/docker-compose.yml`),
    # не публичный хост.
    payment_identity_base_url: str = "http://identity-api:8000"

    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
