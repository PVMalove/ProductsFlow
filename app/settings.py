from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    database_url: str = ""
    secret_key: str = ""
    access_token_ttl_hours: int = 1
    admin_password: str = ""
    cors_allow_origins: list[str] = [
        "http://localhost:5501",
        "http://localhost:7500",
        "http://localhost:8000",
    ]
    minio_endpoint: str = ""
    minio_public_endpoint: str = ""
    minio_root_user: str = ""
    minio_root_password: str = ""
    minio_bucket_name_product: str = ""
    minio_bucket_name_loki: str = ""
    minio_bucket_name_tempo: str = ""

    @property
    def minio_bucket_names(self) -> tuple[str, ...]:
        return (
            self.minio_bucket_name_product,
            self.minio_bucket_name_loki,
            self.minio_bucket_name_tempo,
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
