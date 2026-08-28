from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    identity_jwt_private_key_path: str = ""
    identity_access_token_ttl_hours: int = 1

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
