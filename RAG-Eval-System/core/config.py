"""
配置管理模块
使用 pydantic-settings 进行环境变量管理
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    应用配置类
    从环境变量或 .env 文件加载配置
    """
    
    # OpenAI API 配置
    OPENAI_API_KEY: str = ""
    """OpenAI API 密钥，用于访问大模型服务"""
    
    BASE_URL: str = "https://api.openai.com/v1"
    """大模型 API 基础地址，兼容 OpenAI 格式的第三方服务也可使用"""
    
    MODEL_NAME: str = "qwen-plus"
    """大模型名称，阿里云 DashScope 使用 qwen-turbo/qwen-plus/qwen-max"""
    
    # 文档切分参数
    CHUNK_SIZE: int = 500
    """文档切分时每个文本块的最大字符数"""
    
    CHUNK_OVERLAP: int = 50
    """相邻文本块之间的重叠字符数，保证上下文连续性"""
    
    # 检索参数
    TOP_K_RETRIEVAL: int = 10
    """初次向量检索召回的文档片段数量"""
    
    TOP_N_RERANK: int = 3
    """经过 Reranker 重排后最终保留的文档片段数量"""
    
    class Config:
        """Pydantic 配置"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 全局配置实例
settings = Settings()