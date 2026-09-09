"""工作流集成测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.orchestrator.state import AgentState, TaskStatus
from src.orchestrator.nodes import (
    planner_node,
    level_executor_node,
    level_reviewer_node,
    route_after_review,
)


class TestWorkflowIntegration:
    """工作流集成测试"""

    @pytest.fixture
    def initial_state(self) -> AgentState:
        """初始状态"""
        return {
            "task_id": "test_001",
            "topic": "2026年中国新能源汽车市场格局",
            "plan": None,
            "subtasks": {},
            "execution_levels": [],
            "current_level": 0,
            "completed_results": {},
            "pending_tasks": [],
            "review_feedback": None,
            "retry_count": 0,
            "max_retries": 3,
            "retry_feedback": {},
            "final_result": None,
            "current_stage": "pending",
            "error": None,
            "degraded_tasks": [],
        }

    @pytest.mark.asyncio
    async def test_planner_node(self, initial_state):
        """测试Planner节点"""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '''
        {
            "tasks": {
                "task_0": {
                    "id": "task_0",
                    "name": "行业概览",
                    "description": "梳理行业定义",
                    "depends_on": [],
                    "tools": ["web_search"],
                    "expected_output": "industry_overview"
                },
                "task_1": {
                    "id": "task_1",
                    "name": "市场规模",
                    "description": "收集市场规模数据",
                    "depends_on": [],
                    "tools": ["web_search"],
                    "expected_output": "market_data"
                }
            },
            "execution_levels": [["task_0", "task_1"]]
        }
        '''
        mock_llm.ainvoke.return_value = mock_response

        with patch("src.orchestrator.nodes.get_llm", return_value=mock_llm):
            result = await planner_node(initial_state)

        assert result["current_stage"] == "planning"
        assert len(result["subtasks"]) == 2
        assert len(result["execution_levels"]) == 1

    def test_route_after_review_next_level(self):
        """测试审核后路由 - 下一层级"""
        state = {
            "current_stage": "level_reviewed",
            "retry_count": 0,
            "max_retries": 3,
        }
        assert route_after_review(state) == "next_level"

    def test_route_after_review_aggregate(self):
        """测试审核后路由 - 聚合"""
        state = {
            "current_stage": "all_levels_completed",
            "retry_count": 0,
            "max_retries": 3,
        }
        assert route_after_review(state) == "aggregate"

    def test_route_after_review_retry(self):
        """测试审核后路由 - 重试"""
        state = {
            "current_stage": "retrying",
            "retry_count": 1,
            "max_retries": 3,
        }
        assert route_after_review(state) == "retry_level"

    def test_route_after_review_circuit_breaker(self):
        """测试审核后路由 - 熔断"""
        state = {
            "current_stage": "retrying",
            "retry_count": 3,
            "max_retries": 3,
        }
        assert route_after_review(state) == "aggregate"

    def test_route_after_review_failed(self):
        """测试审核后路由 - 失败"""
        state = {
            "current_stage": "unknown",
            "retry_count": 0,
            "max_retries": 3,
        }
        assert route_after_review(state) == "failed"


class TestDAGExecution:
    """DAG执行测试"""

    def test_dependency_check(self):
        """测试依赖检查"""
        subtasks = {
            "task_0": {"id": "task_0", "status": TaskStatus.COMPLETED.value, "depends_on": []},
            "task_1": {"id": "task_1", "status": TaskStatus.PENDING.value, "depends_on": ["task_0"]},
            "task_2": {"id": "task_2", "status": TaskStatus.PENDING.value, "depends_on": ["task_0"]},
            "task_3": {"id": "task_3", "status": TaskStatus.PENDING.value, "depends_on": ["task_1", "task_2"]},
        }

        # task_1 和 task_2 的前置依赖已完成
        assert all(
            subtasks[dep]["status"] in [TaskStatus.COMPLETED.value, TaskStatus.DEGRADED.value]
            for dep in subtasks["task_1"]["depends_on"]
        )

        # task_3 的前置依赖未完成
        assert not all(
            subtasks[dep]["status"] in [TaskStatus.COMPLETED.value, TaskStatus.DEGRADED.value]
            for dep in subtasks["task_3"]["depends_on"]
        )

    def test_level_execution_order(self):
        """测试层级执行顺序"""
        execution_levels = [["task_0", "task_1"], ["task_2"], ["task_3"]]

        # Level 0: task_0, task_1 并行执行
        assert len(execution_levels[0]) == 2

        # Level 1: task_2 单独执行
        assert len(execution_levels[1]) == 1

        # Level 2: task_3 单独执行
        assert len(execution_levels[2]) == 1
