from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://platform:platform@postgres:5432/platform"
    ai_platform_base_url: str = "http://ai-platform:8001"

    # Dev-only default — override via JWT_SECRET_KEY in production. Rotating
    # this invalidates every issued token.
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
