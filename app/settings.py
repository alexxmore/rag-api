from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Production RAG API"
    environment: str = "local"
    api_keys_file: Path = Path("config/api_keys.yaml")

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "http://localhost:8000"
    openrouter_app_title: str = "Production RAG API"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    vector_backend: str = "faiss"
    vector_index_path: Path = Path("data/vector_index")
    source_path: Path = Path("data/source.md")
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_chunks_collection: str = "rag_chunks"
    qdrant_cache_collection: str = "rag_semantic_cache"

    redis_url: str = "redis://localhost:6379/0"
    sqlite_path: Path = Path("data/usage.sqlite3")

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    max_llm_concurrency: int = 20
    cache_similarity_threshold: float = 0.92
    semantic_cache_ttl_seconds: int = 3600
    max_input_chars: int = Field(default=4000, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
