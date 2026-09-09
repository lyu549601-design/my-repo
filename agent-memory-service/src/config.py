"""Agent 记忆服务配置。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8084, alias="APP_PORT")

    postgres_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/multiagent",
        alias="POSTGRES_URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )

    embedding_provider: str = Field(
        default="local",
        alias="EMBEDDING_PROVIDER",
    )
    embedding_model: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        alias="EMBEDDING_MODEL",
    )
    embedding_dim: int = Field(default=512, alias="EMBEDDING_DIM")
    memory_token_budget: int = Field(default=1600, alias="MEMORY_TOKEN_BUDGET")
    memory_window_size: int = Field(default=3, alias="MEMORY_WINDOW_SIZE")
    memory_retrieval_top_k: int = Field(default=3, alias="MEMORY_RETRIEVAL_TOP_K")
    memory_bm25_weight: float = Field(default=0.3, alias="MEMORY_BM25_WEIGHT")
    memory_semantic_weight: float = Field(default=0.7, alias="MEMORY_SEMANTIC_WEIGHT")
    memory_ttl_seconds: int = Field(default=7200, alias="MEMORY_TTL_SECONDS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
