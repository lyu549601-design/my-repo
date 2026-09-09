"""研报相关数据模型"""

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ReportRequest(BaseModel):
    """研报创建请求"""
    topic: str = Field(..., min_length=2, max_length=500, description="研究主题")
    constraints: Optional[dict[str, Any]] = None
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")


class ReportResponse(BaseModel):
    """研报创建响应"""
    task_id: str
    status: str
    created_at: datetime
    estimated_minutes: int
    websocket_url: str


class ReportStatus(str, Enum):
    """研报状态"""
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportStatusResponse(BaseModel):
    """研报状态查询响应"""
    task_id: str
    topic: str
    status: ReportStatus
    progress: float = Field(ge=0.0, le=1.0)
    current_level: int
    total_levels: int
    subtasks: list[dict[str, Any]]
    degraded_tasks: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class WebSocketMessage(BaseModel):
    """WebSocket消息"""
    type: str = Field(..., pattern="^(progress|level_started|level_completed|review_result|completed|failed)$")
    task_id: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class FinalReport(BaseModel):
    """最终研报"""
    topic: str
    content: str
    sections: list[dict[str, Any]]
    degraded_sections: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    word_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
