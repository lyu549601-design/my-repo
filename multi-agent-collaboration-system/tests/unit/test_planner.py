"""Planner Agent单元测试"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.planner import ReportPlannerAgent
from src.tools.registry import MCPToolRegistry


class TestReportPlannerAgent:
    """Planner Agent测试"""

    @pytest.fixture
    def mock_llm(self):
        """模拟LLM"""
        llm = AsyncMock()
        return llm

    @pytest.fixture
    def mcp_registry(self):
        """MCP工具注册表"""
        return MCPToolRegistry()

    @pytest.fixture
    def planner(self, mock_llm, mcp_registry):
        """创建Planner实例"""
        return ReportPlannerAgent(llm=mock_llm, mcp_registry=mcp_registry)

    @pytest.mark.asyncio
    async def test_plan_success(self, planner, mock_llm):
        """测试成功规划"""
        # 准备LLM响应
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "tasks": {
                "task_0": {
                    "id": "task_0",
                    "name": "行业概览",
                    "description": "梳理行业定义、产业链",
                    "depends_on": [],
                    "tools": ["web_search"],
                    "expected_output": "industry_overview",
                },
                "task_1": {
                    "id": "task_1",
                    "name": "市场规模",
                    "description": "收集市场规模数据",
                    "depends_on": [],
                    "tools": ["web_search"],
                    "expected_output": "market_data",
                },
                "task_2": {
                    "id": "task_2",
                    "name": "竞品分析",
                    "description": "对比主要企业",
                    "depends_on": ["task_0"],
                    "tools": ["web_search", "financial_api"],
                    "expected_output": "competitor_matrix",
                },
            },
            "execution_levels": [["task_0", "task_1"], ["task_2"]],
        }, ensure_ascii=False)
        mock_llm.ainvoke.return_value = mock_response

        # 执行规划
        plan = await planner.plan("2026年中国新能源汽车市场格局")

        # 验证结果
        assert plan.topic == "2026年中国新能源汽车市场格局"
        assert len(plan.tasks) == 3
        assert len(plan.execution_levels) == 2
        assert "task_0" in plan.execution_levels[0]
        assert "task_1" in plan.execution_levels[0]
        assert "task_2" in plan.execution_levels[1]

    @pytest.mark.asyncio
    async def test_plan_invalid_json(self, planner, mock_llm):
        """测试LLM返回无效JSON"""
        mock_response = MagicMock()
        mock_response.content = "invalid json"
        mock_llm.ainvoke.return_value = mock_response

        with pytest.raises(ValueError, match="JSON格式无效"):
            await planner.plan("测试主题")

    @pytest.mark.asyncio
    async def test_plan_circular_dependency(self, planner, mock_llm):
        """测试循环依赖检测"""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "tasks": {
                "task_0": {
                    "id": "task_0",
                    "name": "任务0",
                    "description": "描述",
                    "depends_on": ["task_1"],
                    "tools": [],
                    "expected_output": "test",
                },
                "task_1": {
                    "id": "task_1",
                    "name": "任务1",
                    "description": "描述",
                    "depends_on": ["task_0"],
                    "tools": [],
                    "expected_output": "test",
                },
            },
            "execution_levels": [],
        })
        mock_llm.ainvoke.return_value = mock_response

        with pytest.raises(ValueError, match="循环依赖"):
            await planner.plan("测试主题")

    def test_topological_sort(self, planner):
        """测试拓扑排序"""
        tasks = {
            "t0": {"depends_on": []},
            "t1": {"depends_on": ["t0"]},
            "t2": {"depends_on": ["t0"]},
            "t3": {"depends_on": ["t1", "t2"]},
        }

        levels = planner._topological_sort(tasks)

        assert len(levels) == 3
        assert levels[0] == ["t0"]
        assert set(levels[1]) == {"t1", "t2"}
        assert levels[2] == ["t3"]

    def test_estimate_time(self, planner):
        """测试时间估算"""
        from src.models.task import SubtaskDefinition

        tasks = {
            "t0": SubtaskDefinition(
                id="t0",
                name="任务0",
                description="描述",
                depends_on=[],
                tools=["web_search"],
                expected_output="test",
            ),
        }
        levels = [["t0"]]

        time = planner._estimate_time(tasks, levels)
        assert time > 0
