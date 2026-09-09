"""记忆服务客户端单元测试。"""

import pytest
from httpx import MockTransport, Response

from src.agent_memory.client import MemoryServiceClient
from src.agent_memory.models import EvidenceSummary


class TestMemoryServiceClient:
    @staticmethod
    def make_client(payload):
        async def handler(request):
            if payload is None:
                return Response(200, text="null")
            return Response(200, json=payload)

        return MemoryServiceClient(
            "http://memory:8084",
            transport=MockTransport(handler),
        )

    @pytest.mark.asyncio
    async def test_store_evidence(self):
        summary = EvidenceSummary(claims=["结论A"], summary="结论A")
        client = self.make_client(summary.model_dump(mode="json"))

        result = await client.store_evidence("t1", "task_0", "web_search", {"data": 1})

        assert result.summary == "结论A"
        assert result.claims == ["结论A"]

    @pytest.mark.asyncio
    async def test_get_retry_feedback_empty(self):
        client = self.make_client(None)

        assert await client.get_retry_feedback("t1", "task_0", 1) is None

    @pytest.mark.asyncio
    async def test_build_reviewer_context(self):
        context = {
            "task_id": "t1",
            "topic": "新能源汽车",
            "task_name": "市场规模",
            "task_description": "收集数据",
            "expected_output": "general",
            "current_output_summary": "输出",
            "dependency_summaries": [],
            "top_memories": [],
            "token_budget": 1600,
            "tokens_used": 10,
            "truncated": False,
        }
        client = self.make_client(context)

        result = await client.build_reviewer_context(
            "t1",
            "新能源汽车",
            {"description": "收集数据"},
            "输出",
        )

        assert result.task_id == "t1"
        assert result.tokens_used == 10
