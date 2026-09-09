"""任务相关数据模型"""

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    READY = "ready"
    CLAIMED = "claimed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"


class SubtaskDefinition(BaseModel):
    """子任务定义"""
    id: str
    name: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    expected_output: str


class SubtaskState(BaseModel):
    """子任务运行时状态"""
    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    level: int = 0
    claimed_by: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskResult(BaseModel):
    """任务执行结果"""
    success: bool
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    execution_time: Optional[float] = None
    skipped: bool = False


class ExecutionPlan(BaseModel):
    """执行计划"""
    topic: str
    tasks: dict[str, SubtaskDefinition]
    execution_levels: list[list[str]]
    estimated_time: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    def get_task_level(self, task_id: str) -> int:
        """获取任务所在层级"""
        for level_idx, level_tasks in enumerate(self.execution_levels):
            if task_id in level_tasks:
                return level_idx
        return -1


class ReviewResult(BaseModel):
    """审核结果"""
    passed: bool
    score: float
    degraded: bool = False
    warning: Optional[str] = None
    suggestions: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class MCPRequest(BaseModel):
    """MCP工具调用请求"""
    tool: str
    params: dict[str, Any]
    timeout: int = 120
    request_id: str


class MCPResponse(BaseModel):
    """MCP工具调用响应"""
    success: bool
    result: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    latency_ms: float = 0


class MCPErrorCode(str, Enum):
    """MCP错误码"""
    CONNECTION_FAILED = "CONNECTION_FAILED"
    TIMEOUT = "TIMEOUT"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    INVALID_PARAMS = "INVALID_PARAMS"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
