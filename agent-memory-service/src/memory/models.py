"""记忆系统数据模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Source(BaseModel):
    """来源信息，保留引用能力。"""

    title: str = ""
    url: str = ""
    source: str = ""


class Metric(BaseModel):
    """结构化指标。"""

    name: str
    value: str
    year: str | None = None
    unit: str | None = None


class EvidenceSummary(BaseModel):
    """工具原始结果提炼后的证据摘要。"""

    task_id: str | None = None
    source_task: str | None = None
    claims: list[str] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    summary: str = ""


class MemoryChunk(BaseModel):
    """一条可检索的记忆。"""

    id: str | None = None
    task_id: str
    source_task: str
    chunk_type: Literal["evidence_summary", "review_feedback"] = "evidence_summary"
    content: str
    content_hash: str | None = None
    embedding: list[float] | None = None
    semantic_similarity: float | None = None
    importance: float = 0.5
    access_count: int = 0
    last_access_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class ReviewerContext(BaseModel):
    """Reviewer 审核单个任务所需的完整上下文。"""

    task_id: str
    topic: str
    task_name: str
    task_description: str
    expected_output: str = "general"
    current_output_summary: str
    dependency_summaries: list[EvidenceSummary] = Field(default_factory=list)
    top_memories: list[MemoryChunk] = Field(default_factory=list)
    token_budget: int = 1600
    tokens_used: int = 0
    truncated: bool = False


class ReviewFeedback(BaseModel):
    """审核不通过时写入记忆的结构化反馈。"""

    task_id: str
    source_task: str
    retry_count: int
    score: float
    deductions: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
