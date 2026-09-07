from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, env_file=None, extra="ignore")

    app_env: str = "local"
    celery_broker_url: str = "redis://localhost:6379/0"


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()
