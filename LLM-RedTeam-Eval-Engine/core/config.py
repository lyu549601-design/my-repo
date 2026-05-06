from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用全局配置，支持从 .env 文件或环境变量自动加载。"""

    # OpenAI 兼容 API 密钥
    OPENAI_API_KEY: str = ""

    # API 基础地址，兼容 OpenAI / 本地部署 / 中转站
    BASE_URL: str = "https://api.openai.com/v1"

    # 异步并发信号量上限，控制同时发出的 API 请求数
    MAX_CONCURRENT_REQUESTS: int = 50

    # 目标模型名称（用于 API 调用时的 model 参数）
    TARGET_MODEL: str = "gpt-4o"

    # 评估裁判模型名称（LLM-as-a-Judge 使用）
    JUDGE_MODEL: str = "gpt-4o"

    # 每个评测项由几位裁判独立打分
    JUDGE_COUNT: int = 3

    # 单次 API 请求超时（秒）
    REQUEST_TIMEOUT: int = 60

    # 最大重试次数
    MAX_RETRIES: int = 3

    # 重试退避基础间隔（秒）
    RETRY_BACKOFF: float = 1.0

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """获取全局单例配置实例（带缓存，避免重复加载）。"""
    return Settings()
