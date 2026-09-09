"""Reviewer Agent单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.reviewer import ReviewerAgent
from src.models.task import TaskResult
from src.agent_memory.models import EvidenceSummary, Metric, ReviewerContext


class TestReviewerAgent:
    """Reviewer Agent测试"""

    @pytest.fixture
    def mock_llm(self):
        """模拟LLM"""
        llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"accuracy": 0.9, "logic": 0.85, "completeness": 0.8, "depth": 0.75, "consistency": 0.9, "conflicts": [], "missing_data": [], "comments": "质量良好"}'
        llm.ainvoke.return_value = mock_response
        return llm

    @pytest.fixture
    def reviewer(self, mock_llm):
        """创建Reviewer实例"""
        return ReviewerAgent(
            llm=mock_llm,
            quality_threshold=0.8,
            max_retries=3,
        )

    @pytest.fixture
    def review_context(self):
        """带依赖摘要的审核上下文"""
        return ReviewerContext(
            task_id="task_001",
            topic="2026年新能源汽车市场",
            task_name="市场规模",
            task_description="收集市场规模数据",
            current_output_summary="2026年市场规模预计达到1000亿元",
            dependency_summaries=[
                EvidenceSummary(
                    source_task="task_0",
                    claims=["行业处于快速增长期"],
                    metrics=[Metric(name="market_size", value="1000", year="2026")],
                    summary="行业快速增长",
                )
            ],
        )

    @pytest.mark.asyncio
    async def test_review_pass(self, reviewer, mock_llm, review_context):
        """测试审核通过"""
        task_result = TaskResult(
            success=True,
            data={"task_id": "task_1", "tool_results": {"web_search": {"data": "test"}}},
        )
        task = {"id": "task_1", "name": "市场规模", "description": "收集市场规模数据", "expected_output": "general"}

        result = await reviewer.review(task_result, task, retry_count=0, context=review_context)

        assert result.passed is True
        assert result.score >= 0.8
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_review_fail(self, reviewer, mock_llm, review_context):
        """测试审核失败"""
        mock_response = MagicMock()
        mock_response.content = '{"accuracy": 0.3, "logic": 0.4, "completeness": 0.5, "depth": 0.3, "consistency": 0.4, "conflicts": ["规模数值矛盾"], "missing_data": ["市场份额"], "comments": "质量较差"}'
        mock_llm.ainvoke.return_value = mock_response

        task_result = TaskResult(
            success=True,
            data={"task_id": "task_1"},
        )
        task = {"id": "task_1", "name": "市场规模", "description": "收集市场规模数据", "expected_output": "general"}

        result = await reviewer.review(task_result, task, retry_count=0, context=review_context)

        assert result.passed is False
        assert result.score < 0.8
        assert len(result.suggestions) > 0
        assert "review_feedback" in result.details

    @pytest.mark.asyncio
    async def test_review_fail_stores_feedback(self, mock_llm, review_context):
        """测试不通过时反馈写入记忆"""
        memory_manager = AsyncMock()
        reviewer = ReviewerAgent(
            llm=mock_llm,
            quality_threshold=0.8,
            max_retries=3,
            memory_manager=memory_manager,
        )
        mock_response = MagicMock()
        mock_response.content = '{"accuracy": 0.3, "logic": 0.4, "completeness": 0.5, "depth": 0.3, "consistency": 0.4, "conflicts": [], "missing_data": ["市场份额"], "comments": "质量较差"}'
        mock_llm.ainvoke.return_value = mock_response

        task_result = TaskResult(success=True, data={"task_id": "task_1"})
        task = {"id": "task_1", "name": "市场规模", "description": "收集数据", "expected_output": "general"}
        await reviewer.review(task_result, task, retry_count=1, context=review_context)

        memory_manager.store_review_feedback.assert_awaited_once()
        stored_feedback = memory_manager.store_review_feedback.await_args.args[0]
        assert stored_feedback.retry_count == 2
        assert "市场份额" in stored_feedback.missing_data

    @pytest.mark.asyncio
    async def test_review_circuit_breaker(self, reviewer):
        """测试熔断机制"""
        task_result = TaskResult(success=False, error="执行失败")
        task = {"id": "task_0", "name": "测试", "description": "描述", "expected_output": "general"}

        result = await reviewer.review(task_result, task, retry_count=3)

        assert result.passed is True  # 降级放行
        assert result.degraded is True
        assert result.score == 0.6
        assert "降级放行" in result.warning

    @pytest.mark.asyncio
    async def test_review_llm_error(self, reviewer, mock_llm, review_context):
        """测试LLM调用失败"""
        mock_llm.ainvoke.side_effect = Exception("LLM调用失败")

        task_result = TaskResult(
            success=True,
            data={"task_id": "task_0"},
        )
        task = {"id": "task_0", "name": "测试", "description": "描述", "expected_output": "general"}

        result = await reviewer.review(task_result, task, retry_count=0, context=review_context)

        assert result.passed is False

    def test_calculate_score(self, reviewer):
        """测试分数计算"""
        auto_checks = {"completeness": 0.9, "format": 1.0, "freshness": 0.8, "consistency": 0.9}
        llm_check = {
            "accuracy": 0.9,
            "logic": 0.85,
            "completeness": 0.8,
            "depth": 0.75,
            "consistency": 0.9,
        }

        score = reviewer._calculate_score(auto_checks, llm_check)

        assert 0.0 <= score <= 1.0
        assert score > 0.8

    def test_check_consistency_without_context(self, reviewer):
        """无上下文时一致性不能虚高"""
        result = TaskResult(success=True, data={"key": "value"})
        assert reviewer._check_consistency(result, None) == 0.5

    def test_check_consistency_conflict(self, reviewer, review_context):
        """依赖数值与当前输出矛盾时一致性为0"""
        result = TaskResult(success=True, data={"market_size": "999"})
        assert reviewer._check_consistency(result, review_context) == 0.0

    def test_check_consistency_match(self, reviewer, review_context):
        """依赖数值一致时一致性应通过"""
        result = TaskResult(success=True, data={"market_size": "1000"})
        assert reviewer._check_consistency(result, review_context) == 0.8

    def test_check_completeness(self, reviewer):
        """测试完整性检查"""
        result = TaskResult(success=True, data={"expected_output": "general"})
        task = {"expected_output": "general"}
        assert reviewer._check_completeness(result, task) == 1.0

        result = TaskResult(success=True, data=None)
        assert reviewer._check_completeness(result, task) == 0.0

    def test_check_format(self, reviewer):
        """测试格式检查"""
        result = TaskResult(success=True, data={"key": "value"})
        assert reviewer._check_format(result) == 1.0

        result = TaskResult(success=True, data=None)
        assert reviewer._check_format(result) == 0.0

    def test_generate_suggestions(self, reviewer):
        """测试建议生成"""
        auto_checks = {"completeness": 0.5}
        llm_check = {"accuracy": 0.6, "logic": 0.8, "depth": 0.8, "consistency": 0.9}

        suggestions = reviewer._generate_suggestions(auto_checks, llm_check, passed=False)
        assert len(suggestions) > 0

        suggestions = reviewer._generate_suggestions(auto_checks, llm_check, passed=True)
        assert "质量达标" in suggestions[0]
