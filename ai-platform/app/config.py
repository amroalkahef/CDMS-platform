from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://platform:platform@postgres:5432/platform"

    llm_api_key: str = ""
    llm_base_url: str = ""
    chat_model: str = "gpt-4o-mini"

    # Embeddings are looked up on a separate client because not every LLM
    # provider (e.g. Groq) also serves an embeddings endpoint. Falls back to
    # the main llm_api_key/llm_base_url when unset.
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    backend_base_url: str = "http://backend:8000"

    documents_storage_path: str = "/data/documents"


@lru_cache
def get_settings() -> Settings:
    return Settings()
