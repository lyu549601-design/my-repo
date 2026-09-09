"""RAG 系统数据模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserContext(BaseModel):
    """当前提问用户的权限上下文。"""

    user_id: str
    department_ids: list[str] = Field(default_factory=list)
    role_ids: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)


class Document(BaseModel):
    """已入库文档。"""

    id: str
    title: str
    file_path: str = ""
    file_type: str = ""
    page_count: int = 0
    project_folder_id: str | None = None
    visible_department_ids: list[str] = Field(default_factory=list)
    visible_role_ids: list[str] = Field(default_factory=list)
    status: str = "ready"
    uploaded_by: str = ""
    uploaded_at: datetime = Field(default_factory=utcnow)


class DocumentChunk(BaseModel):
    """文档切片。"""

    id: str
    document_id: str
    page: int = 1
    chapter: str = ""
    start_offset: int = 0
    end_offset: int = 0
    content: str
    content_hash: str = ""
    embedding: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    """检索返回片段。"""

    chunk_id: str
    document_id: str
    document_name: str
    page: int
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    """答案引用。"""

    ref_id: int
    document_id: str
    document_name: str
    page: int
    content: str


class QAResult(BaseModel):
    """问答结果。"""

    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = 0.0
    rejected: bool = False
    rejection_reason: str = ""
