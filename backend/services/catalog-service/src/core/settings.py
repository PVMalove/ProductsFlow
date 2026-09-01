from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    catalog_database_url: str = ""
    # Базовый URL identity-service для `IdentityClient` (JWKS-верификация,
    # `GET /api/v1/users/me`, ADR 0011/0012) — имя сервиса compose-сети
    # (`backend/docker-compose.yml`), не публичный хост.
    catalog_identity_base_url: str = "http://identity-api:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
