"""API路由"""

import uuid
import structlog
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from src.models.report import ReportRequest, ReportResponse, ReportStatusResponse
from src.orchestrator.graph import create_report_agent_graph
from src.orchestrator.nodes import get_memory_manager
from src.orchestrator.state import AgentState
from src.communication.event_bus import EventBus, Event
from src.config import get_settings

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["reports"])

# 任务存储（生产环境应使用数据库）
_tasks: dict[str, dict[str, Any]] = {}
_event_bus = EventBus()


class TaskStore:
    """任务存储（简化版，生产环境应使用PostgreSQL）"""

    @staticmethod
    def create(task_id: str, topic: str) -> dict[str, Any]:
        task = {
            "task_id": task_id,
            "topic": topic,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "state": None,
            "result": None,
            "error": None,
        }
        _tasks[task_id] = task
        return task

    @staticmethod
    def get(task_id: str) -> dict[str, Any] | None:
        return _tasks.get(task_id)

    @staticmethod
    def update(task_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        if task_id in _tasks:
            _tasks[task_id].update(updates)
            _tasks[task_id]["updated_at"] = datetime.utcnow().isoformat()
            return _tasks[task_id]
        return None

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        return list(_tasks.values())


@router.post("/reports", response_model=ReportResponse)
async def create_report(request: ReportRequest, background_tasks: BackgroundTasks):
    """创建研报任务
    
    提交一个研究主题，系统会自动分解任务并执行。
    返回任务ID和WebSocket进度推送地址。
    """
    task_id = str(uuid.uuid4())
    settings = get_settings()

    # 创建任务记录
    task = TaskStore.create(task_id, request.topic)

    # 估算时间（分钟）
    estimated_minutes = 20

    # 后台执行任务
    background_tasks.add_task(execute_report_task, task_id, request.topic)

    logger.info("api.report_created", task_id=task_id, topic=request.topic)

    return ReportResponse(
        task_id=task_id,
        status="pending",
        created_at=datetime.fromisoformat(task["created_at"]),
        estimated_minutes=estimated_minutes,
        websocket_url=f"ws://localhost:{settings.app_port}/ws/reports/{task_id}",
    )


@router.get("/reports/{task_id}", response_model=ReportStatusResponse)
async def get_report_status(task_id: str):
    """查询研报任务状态"""
    task = TaskStore.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    state = task.get("state", {})

    return ReportStatusResponse(
        task_id=task_id,
        topic=task["topic"],
        status=task["status"],
        progress=_calculate_progress(state),
        current_level=state.get("current_level", 0) if state else 0,
        total_levels=len(state.get("execution_levels", [])) if state else 0,
        subtasks=_format_subtasks(state.get("subtasks", {})) if state else [],
        degraded_tasks=state.get("degraded_tasks", []) if state else [],
        error=task.get("error"),
        result=task.get("result"),
        created_at=datetime.fromisoformat(task["created_at"]),
        updated_at=datetime.fromisoformat(task["updated_at"]),
    )


@router.get("/reports")
async def list_reports():
    """列出所有研报任务"""
    tasks = TaskStore.list_all()
    return {"tasks": tasks, "total": len(tasks)}


@router.delete("/reports/{task_id}")
async def delete_report(task_id: str):
    """删除研报任务"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    del _tasks[task_id]
    return {"message": "任务已删除"}


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


async def execute_report_task(task_id: str, topic: str):
    """后台执行研报任务"""
    try:
        # 更新状态为执行中
        TaskStore.update(task_id, {"status": "executing"})

        # 创建初始状态
        initial_state: AgentState = {
            "task_id": task_id,
            "topic": topic,
            "plan": None,
            "subtasks": {},
            "execution_levels": [],
            "current_level": 0,
            "completed_results": {},
            "pending_tasks": [],
            "review_feedback": None,
            "retry_count": 0,
            "max_retries": get_settings().max_retries,
            "retry_feedback": {},
            "final_result": None,
            "current_stage": "pending",
            "error": None,
            "degraded_tasks": [],
        }

        memory_manager = get_memory_manager()
        try:
            # 创建并执行状态图
            graph = create_report_agent_graph()
            final_state = await graph.ainvoke(initial_state)
        finally:
            try:
                await memory_manager.clear_task(task_id)
            except Exception as exc:
                logger.warning("memory.clear_task_failed", task_id=task_id, error=str(exc))

        # 更新任务状态
        if final_state.get("current_stage") == "completed":
            TaskStore.update(task_id, {
                "status": "completed",
                "state": final_state,
                "result": final_state.get("final_result"),
            })
            logger.info("api.report_completed", task_id=task_id)
        else:
            TaskStore.update(task_id, {
                "status": "failed",
                "state": final_state,
                "error": final_state.get("error", "未知错误"),
            })
            logger.error("api.report_failed", task_id=task_id, error=final_state.get("error"))

    except Exception as e:
        logger.error("api.report_execution_error", task_id=task_id, error=str(e))
        TaskStore.update(task_id, {
            "status": "failed",
            "error": str(e),
        })


def _calculate_progress(state: dict[str, Any] | None) -> float:
    """计算进度"""
    if not state:
        return 0.0

    current_stage = state.get("current_stage", "pending")
    stage_progress = {
        "pending": 0.0,
        "planning": 0.1,
        "executing": 0.5,
        "reviewing": 0.7,
        "aggregating": 0.9,
        "completed": 1.0,
        "failed": 0.0,
    }

    base_progress = stage_progress.get(current_stage, 0.0)

    # 根据子任务完成情况细化进度
    subtasks = state.get("subtasks", {})
    if subtasks and current_stage == "executing":
        completed = sum(1 for t in subtasks.values() if t.get("status") in ["completed", "degraded"])
        total = len(subtasks)
        if total > 0:
            task_progress = completed / total
            base_progress = 0.2 + task_progress * 0.6

    return min(base_progress, 1.0)


def _format_subtasks(subtasks: dict[str, Any]) -> list[dict[str, Any]]:
    """格式化子任务状态"""
    return [
        {
            "id": task_id,
            "name": task.get("name", ""),
            "status": task.get("status", "pending"),
            "level": task.get("level", 0),
            "retry_count": task.get("retry_count", 0),
            "error": task.get("error"),
        }
        for task_id, task in subtasks.items()
    ]
