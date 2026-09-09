"""测试配置"""

import pytest
import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from src.config import Settings


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings() -> Settings:
    """模拟配置"""
    return Settings(
        OPENAI_API_KEY="test-key",
        OPENAI_MODEL="gpt-4o",
        REDIS_URL="redis://localhost:6379/0",
        POSTGRES_URL="postgresql://test:test@localhost:5432/test",
        MAX_RETRIES=3,
        QUALITY_THRESHOLD=0.8,
    )


@pytest.fixture
def mock_llm():
    """模拟LLM"""
    llm = AsyncMock()
    response = MagicMock()
    response.content = '{"tasks": {}, "execution_levels": []}'
    llm.ainvoke.return_value = response
    return llm


@pytest.fixture
def mock_mcp_client():
    """模拟MCP客户端"""
    client = AsyncMock()
    client.call.return_value = MagicMock(
        success=True,
        result={"data": "test"},
        latency_ms=100,
    )
    return client


@pytest.fixture
def mock_redis():
    """模拟Redis"""
    redis = AsyncMock()
    redis.eval.return_value = 1
    redis.hget.return_value = None
    redis.hset.return_value = True
    redis.delete.return_value = True
    return redis
