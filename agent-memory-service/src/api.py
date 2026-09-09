"""Agent 记忆服务 HTTP API。"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.memory.manager import MemoryManager
from src.memory.models import EvidenceSummary, ReviewFeedback, ReviewerContext

logger = structlog.get_logger()

app = FastAPI(
    title="Agent 记忆管理系统",
    description="任务内短期/长期分层记忆、混合检索、摘要压缩与审核反馈服务",
    version="1.0.0",
)

_manager: MemoryManager | None = None


def get_manager() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager.from_settings()
    return _manager


class StoreEvidenceRequest(BaseModel):
    source_task: str
    tool_name: str
    raw_result: Any
    importance: float = 0.5


class ReviewerContextRequest(BaseModel):
    topic: str
    task: dict[str, Any]
    current_output_summary: str
    dependency_results: dict[str, Any] | None = None
    token_budget: int | None = None


@app.post("/tasks/{task_id}/evidence", response_model=EvidenceSummary)
async def store_evidence(task_id: str, request: StoreEvidenceRequest):
    return await get_manager().store_evidence(
        task_id=task_id,
        source_task=request.source_task,
        tool_name=request.tool_name,
        raw_result=request.raw_result,
        importance=request.importance,
    )


@app.post("/tasks/{task_id}/feedback")
async def store_feedback(task_id: str, feedback: ReviewFeedback):
    if feedback.task_id != task_id:
        feedback.task_id = task_id
    await get_manager().store_review_feedback(feedback)
    return {"status": "stored", "task_id": task_id}


@app.get("/tasks/{task_id}/retry-feedback", response_model=ReviewFeedback | None)
async def get_retry_feedback(task_id: str, source_task: str, retry_count: int):
    return await get_manager().get_retry_feedback(
        task_id=task_id,
        source_task=source_task,
        retry_count=retry_count,
    )


@app.get("/tasks/{task_id}/evidence/{source_task}", response_model=EvidenceSummary | None)
async def get_evidence_summary(task_id: str, source_task: str):
    return await get_manager().get_evidence_summary(task_id, source_task)


@app.post("/tasks/{task_id}/reviewer-context", response_model=ReviewerContext)
async def build_reviewer_context(task_id: str, request: ReviewerContextRequest):
    return await get_manager().build_reviewer_context(
        task_id=task_id,
        topic=request.topic,
        task=request.task,
        current_output_summary=request.current_output_summary,
        dependency_results=request.dependency_results,
        token_budget=request.token_budget,
    )


@app.delete("/tasks/{task_id}")
async def clear_task(task_id: str):
    await get_manager().clear_task(task_id)
    return {"status": "cleared", "task_id": task_id}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "agent-memory-service"}
