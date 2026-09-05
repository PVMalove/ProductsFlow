from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    identity_jwt_private_key_path: str = ""
    identity_access_token_ttl_hours: int = 1
    identity_database_url: str = ""
    identity_amqp_url: str = "amqp://guest:guest@localhost:5672/"
    identity_outbox_poll_interval_seconds: float = 5.0
    admin_email: str = ""
    admin_password: str = ""

    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
