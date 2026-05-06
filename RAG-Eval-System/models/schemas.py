"""
数据模型定义模块
定义 API 请求和响应的 Pydantic 模型
"""

from pydantic import BaseModel, Field
from typing import List


class AskRequest(BaseModel):
    """用户提问请求模型"""
    
    query: str = Field(..., description="用户提出的问题", min_length=1)
    """用户提出的问题文本"""


class SourceNode(BaseModel):
    """检索到的文档片段模型"""
    
    content: str = Field(..., description="文档片段的文本内容")
    """从知识库中检索到的相关文档片段内容"""
    
    score: float = Field(..., description="与查询问题的相关性得分，范围 0-1")
    """经过 Reranker 计算的相关性分数，值越高越相关"""


class EvalScore(BaseModel):
    """RAG 评估结果模型"""
    
    faithfulness_score: int = Field(
        ..., 
        description="忠实度评分（1-5），衡量答案是否基于检索到的文档内容，避免幻觉",
        ge=1,
        le=5
    )
    """忠实度评分：1=完全幻觉，5=完全基于文档"""
    
    relevance_score: int = Field(
        ..., 
        description="相关性评分（1-5），衡量答案与用户问题的匹配程度",
        ge=1,
        le=5
    )
    """相关性评分：1=完全不相关，5=完全回答了问题"""
    
    reasoning: str = Field(..., description="评分理由说明")
    """大模型给出的具体评分理由和分析"""


class AskResponse(BaseModel):
    """问答响应模型"""
    
    answer: str = Field(..., description="大模型生成的回答文本")
    """基于检索文档生成的最终答案"""
    
    sources: List[SourceNode] = Field(default_factory=list, description="检索到的参考文档片段列表")
    """用于生成答案的参考文档片段，按相关性排序"""
    
    evaluation: EvalScore = Field(..., description="答案质量评估结果")
    """对生成答案的自动化评估结果，包含忠实度和相关性评分"""