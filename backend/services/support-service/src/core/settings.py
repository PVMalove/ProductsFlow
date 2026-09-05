from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    support_database_url: str = ""
    support_amqp_url: str = "amqp://guest:guest@localhost:5672/"
    support_jwt_public_key_path: str = ""
    support_jwt_public_key: str = ""
    support_jwt_issuer: str = "identity-service"

    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
