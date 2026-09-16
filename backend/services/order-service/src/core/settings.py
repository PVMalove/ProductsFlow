from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    order_database_url: str = ""
    # Базовый URL identity-service для `IdentityClient` (JWKS-верификация,
    # ADR 0005/0011) — имя сервиса compose-сети (`backend/docker-compose.yml`),
    # не публичный хост.
    order_identity_base_url: str = "http://identity-api:8000"
    # Базовый URL catalog-service для авторитетного checkout quote
    # (issue #372, D9) — имя сервиса compose-сети, не публичный хост.
    order_catalog_base_url: str = "http://catalog-api:8000"
    order_amqp_url: str = "amqp://guest:guest@localhost:5672/"
    # issue #372, D6/D8: интервал периодического дренажа reservation_outbox
    # в order-worker — тот же приём, что `catalog_outbox_poll_interval_seconds`.
    order_outbox_poll_interval_seconds: float = 5.0

    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
