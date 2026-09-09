"""LangGraph状态定义"""

from typing import TypedDict, Annotated, Optional, Any
from enum import Enum


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    READY = "ready"
    CLAIMED = "claimed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """合并两个字典"""
    return {**left, **right}


class SubtaskState(TypedDict):
    """子任务状态"""
    id: str
    name: str
    status: str  # TaskStatus
    depends_on: list[str]
    level: int
    claimed_by: Optional[str]
    result: Optional[dict[str, Any]]
    error: Optional[str]
    retry_count: int


class AgentState(TypedDict):
    """LangGraph状态定义
    
    职责边界：
    - LangGraph StateGraph: 负责内部状态流转、条件路由
    - EventBus/WebSocket: 仅负责外部广播，不参与内部调度
    - LangGraph Checkpointer: 负责图状态快照持久化
    - Redis: 负责分布式任务认领锁
    """
    # 任务基础信息
    task_id: str
    topic: str

    # DAG结构
    plan: Optional[dict[str, Any]]
    subtasks: dict[str, Any]  # SubtaskState映射
    execution_levels: list[list[str]]

    # 执行状态
    current_level: int
    completed_results: Annotated[dict[str, Any], merge_dicts]
    pending_tasks: list[str]

    # 审核状态
    review_feedback: Optional[dict[str, Any]]
    retry_count: int
    max_retries: int
    retry_feedback: Optional[dict[str, Any]]

    # 最终输出
    final_result: Optional[dict[str, Any]]
    current_stage: str
    error: Optional[str]
    degraded_tasks: list[str]
