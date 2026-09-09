"""RAG 系统配置。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8090, alias="APP_PORT")

    postgres_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/ragqa",
        alias="POSTGRES_URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )

    embedding_provider: str = Field(default="local", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        alias="EMBEDDING_MODEL",
    )
    embedding_dim: int = Field(default=512, alias="EMBEDDING_DIM")

    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        alias="DEEPSEEK_BASE_URL",
    )
    deepseek_model: str = Field(
        default="deepseek-v4-flash",
        alias="DEEPSEEK_MODEL",
    )

    retrieval_top_k: int = Field(default=5, alias="RAG_RETRIEVAL_TOP_K")
    semantic_expansion: int = Field(default=5, alias="RAG_SEMANTIC_EXPANSION")
    bm25_weight: float = Field(default=0.3, alias="RAG_BM25_WEIGHT")
    semantic_weight: float = Field(default=0.7, alias="RAG_SEMANTIC_WEIGHT")
    confidence_threshold: float = Field(default=0.65, alias="RAG_CONFIDENCE_THRESHOLD")
    max_chunk_tokens: int = Field(default=500, alias="RAG_MAX_CHUNK_TOKENS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
