from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = ""
    secret_key: str = ""
    access_token_ttl_hours: int = 1
    admin_password: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
