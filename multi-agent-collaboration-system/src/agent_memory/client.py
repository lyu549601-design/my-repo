"""Agent 记忆服务 HTTP 客户端。"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from .models import EvidenceSummary, ReviewFeedback, ReviewerContext

logger = structlog.get_logger()


class MemoryServiceClient:
    """与 MemoryManager 保持同构方法签名，降低主系统接入成本。"""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def store_evidence(
        self,
        task_id: str,
        source_task: str,
        tool_name: str,
        raw_result: Any,
        importance: float = 0.5,
    ) -> EvidenceSummary:
        response = await self._client.post(
            f"{self.base_url}/tasks/{task_id}/evidence",
            json={
                "source_task": source_task,
                "tool_name": tool_name,
                "raw_result": raw_result,
                "importance": importance,
            },
        )
        response.raise_for_status()
        return EvidenceSummary.model_validate(response.json())

    async def store_review_feedback(self, feedback: ReviewFeedback) -> None:
        response = await self._client.post(
            f"{self.base_url}/tasks/{feedback.task_id}/feedback",
            json=feedback.model_dump(mode="json"),
        )
        response.raise_for_status()

    async def get_retry_feedback(
        self,
        task_id: str,
        source_task: str,
        retry_count: int,
    ) -> ReviewFeedback | None:
        response = await self._client.get(
            f"{self.base_url}/tasks/{task_id}/retry-feedback",
            params={"source_task": source_task, "retry_count": retry_count},
        )
        response.raise_for_status()
        data = response.json()
        return ReviewFeedback.model_validate(data) if data else None

    async def build_reviewer_context(
        self,
        task_id: str,
        topic: str,
        task: dict[str, Any],
        current_output_summary: str,
        dependency_results: dict[str, Any] | None = None,
        token_budget: int | None = None,
    ) -> ReviewerContext:
        response = await self._client.post(
            f"{self.base_url}/tasks/{task_id}/reviewer-context",
            json={
                "topic": topic,
                "task": task,
                "current_output_summary": current_output_summary,
                "dependency_results": dependency_results,
                "token_budget": token_budget,
            },
        )
        response.raise_for_status()
        return ReviewerContext.model_validate(response.json())

    async def clear_task(self, task_id: str) -> None:
        response = await self._client.delete(f"{self.base_url}/tasks/{task_id}")
        response.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()
