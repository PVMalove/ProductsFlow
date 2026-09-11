from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    inventory_database_url: str = ""
    inventory_amqp_url: str = "amqp://guest:guest@localhost:5672/"
    # Базовый URL identity-service для `IdentityClient` (JWKS-верификация,
    # `GET /api/v1/users/me`, ADR 0005/0011) — имя сервиса compose-сети
    # (`backend/docker-compose.yml`), не публичный хост.
    inventory_identity_base_url: str = "http://identity-api:8000"
    inventory_outbox_poll_interval_seconds: float = 5.0

    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
