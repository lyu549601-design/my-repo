"""应用配置管理"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""
    
    # Application
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    
    # LLM
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_reasoning_effort: Optional[str] = Field(
        default=None,
        alias="OPENAI_REASONING_EFFORT",
    )
    
    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")
    
    # PostgreSQL
    postgres_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/multiagent",
        alias="POSTGRES_URL"
    )

    # Agent Memory Service
    memory_service_url: str = Field(
        default="http://localhost:8084",
        alias="MEMORY_SERVICE_URL",
    )
    
    # MCP Server API Keys
    serpapi_key: str = Field(default="", alias="SERPAPI_KEY")
    tushare_token: str = Field(default="", alias="TUSHARE_TOKEN")
    
    # Langfuse
    langfuse_public_key: Optional[str] = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")
    
    # Agent Settings
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    task_timeout: int = Field(default=3600, alias="TASK_TIMEOUT")
    quality_threshold: float = Field(default=0.8, alias="QUALITY_THRESHOLD")
    
    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    
    # MCP Server URLs
    search_mcp_url: str = Field(default="http://localhost:8081", alias="SEARCH_MCP_URL")
    financial_mcp_url: str = Field(default="http://localhost:8082", alias="FINANCIAL_MCP_URL")
    cleaner_mcp_url: str = Field(default="http://localhost:8083", alias="CLEANER_MCP_URL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
