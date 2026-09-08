from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Runtime settings loaded only from explicit environment variables."""

    model_config = SettingsConfigDict(
        case_sensitive=False, env_file=None, extra="ignore", env_ignore_empty=True
    )

    app_env: str = "local"
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "trade_workbench"
    database_user: str = "trade_workbench"
    database_password: str = "local-dev-only-change-me"
    redis_host: str = "localhost"
    redis_port: int = 6379
    minio_host: str = "localhost"
    minio_port: int = 9000
    minio_access_key: str = "localminio"
    minio_secret_key: str = "local-dev-only-change-me"
    minio_bucket: str = "trade-workbench-documents"
    minio_secure: bool = False
    minio_public_endpoint: str | None = None
    minio_public_secure: bool = False
    minio_region: str = "us-east-1"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = Field(default=None, max_length=100)
    ai_provider: Literal["openai", "deepseek"] = "openai"
    deepseek_api_key: SecretStr | None = None
    deepseek_model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    ai_input_usd_per_million: Decimal | None = Field(default=None, ge=0)
    ai_output_usd_per_million: Decimal | None = Field(default=None, ge=0)
    dependency_timeout_seconds: float = 1.0
    oidc_issuer: str = "https://auth.example.invalid/oidc"
    oidc_audience: str = "https://api.trade-workbench.local"
    oidc_jwks_url: str = "https://auth.example.invalid/oidc/jwks"
    oidc_signing_algorithm: Literal["RS256", "ES384"] = "RS256"

    @property
    def ai_model_identity(self) -> str:
        if self.ai_provider == "deepseek":
            return f"deepseek/{self.deepseek_model}"
        return self.openai_model or "unconfigured"

    @property
    def database_url(self) -> str:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.database_user,
            password=self.database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
