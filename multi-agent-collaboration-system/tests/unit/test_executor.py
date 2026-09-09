"""Executor Agent单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.executor import ExecutorAgent, ExecutorAgentPool
from src.models.task import TaskResult, MCPResponse


class TestExecutorAgent:
    """Executor Agent测试"""

    @pytest.fixture
    def mock_mcp_client(self):
        """模拟MCP客户端"""
        client = AsyncMock()
        client.call.return_value = MCPResponse(
            success=True,
            result={"data": "test_result"},
            latency_ms=100,
        )
        return client

    @pytest.fixture
    def mock_task_lock(self):
        """模拟任务锁"""
        lock = AsyncMock()
        lock.try_claim.return_value = True
        lock.release.return_value = True
        return lock

    @pytest.fixture
    def executor(self, mock_mcp_client, mock_task_lock):
        """创建Executor实例"""
        return ExecutorAgent(
            agent_id="test_executor",
            mcp_client=mock_mcp_client,
            task_lock=mock_task_lock,
        )

    @pytest.mark.asyncio
    async def test_execute_success(self, executor, mock_mcp_client):
        """测试成功执行"""
        task = {
            "id": "task_0",
            "name": "测试任务",
            "description": "测试描述",
            "tools": ["web_search"],
            "expected_output": "general",
            "depends_on": [],
        }
        context = {"completed_results": {}, "topic": "测试"}

        result = await executor.execute(task, context)

        assert result.success is True
        assert result.data is not None
        assert result.task_id == "task_0"
        assert result.agent_id == "test_executor"

    @pytest.mark.asyncio
    async def test_execute_claim_failed(self, executor, mock_task_lock):
        """测试任务认领失败"""
        mock_task_lock.try_claim.return_value = False

        task = {"id": "task_0", "name": "测试", "tools": [], "depends_on": []}
        context = {}

        result = await executor.execute(task, context)

        assert result.success is False
        assert result.skipped is True

    @pytest.mark.asyncio
    async def test_execute_mcp_error(self, executor, mock_mcp_client):
        """测试MCP调用失败"""
        from src.tools.mcp_client import MCPToolError
        from src.models.task import MCPErrorCode

        mock_mcp_client.call.side_effect = MCPToolError(
            tool="web_search",
            error_code=MCPErrorCode.CONNECTION_FAILED,
            message="连接失败",
        )

        task = {
            "id": "task_0",
            "name": "测试",
            "tools": ["web_search"],
            "expected_output": "general",
            "depends_on": [],
        }
        context = {}

        result = await executor.execute(task, context)

        assert result.success is False
        assert "MCP工具调用失败" in result.error

    @pytest.mark.asyncio
    async def test_execute_validation_failed(self, executor, mock_mcp_client):
        """测试输出验证失败"""
        # 返回空结果，验证会失败
        mock_mcp_client.call.return_value = MCPResponse(
            success=True,
            result=None,
        )

        task = {
            "id": "task_0",
            "name": "测试",
            "tools": ["web_search"],
            "expected_output": "final_report",
            "depends_on": [],
        }
        context = {}

        result = await executor.execute(task, context)

        # 验证失败会返回错误
        assert result.success is False

    def test_apply_retry_feedback(self, executor):
        """测试审核反馈转换为补充提示"""
        description = "收集市场规模数据"
        context = {
            "retry_feedback": {
                "missing_data": ["市场份额"],
                "conflicts": ["2026年规模数值矛盾"],
                "suggestions": ["补充市场份额数据"],
            }
        }

        enriched = executor._apply_retry_feedback(description, context)

        assert "收集市场规模数据" in enriched
        assert "市场份额" in enriched
        assert "2026年规模数值矛盾" in enriched
        assert "补充市场份额数据" in enriched

    def test_apply_retry_feedback_empty(self, executor):
        """无反馈时保持原描述"""
        description = "原始描述"
        assert executor._apply_retry_feedback(description, {}) == "原始描述"

    def test_collect_dependencies(self, executor):
        """测试依赖收集"""
        task = {"depends_on": ["task_0", "task_1"]}
        context = {
            "completed_results": {
                "task_0": {"data": "result_0"},
                "task_1": {"data": "result_1"},
            }
        }

        deps = executor._collect_dependencies(task, context)

        assert "task_0" in deps
        assert "task_1" in deps
        assert deps["task_0"]["data"] == "result_0"

    def test_assemble_result(self, executor):
        """测试结果组装"""
        task = {
            "id": "task_0",
            "name": "测试任务",
            "expected_output": "general",
        }
        tool_results = {"web_search": {"data": "search_result"}}

        result = executor._assemble_result(task, tool_results)

        assert result["task_id"] == "task_0"
        assert result["task_name"] == "测试任务"
        assert "tool_results" in result
        assert "assembled_at" in result


class TestExecutorAgentPool:
    """Executor Agent池测试"""

    @pytest.fixture
    def mock_mcp_client(self):
        client = AsyncMock()
        client.call.return_value = MCPResponse(
            success=True,
            result={"data": "test"},
        )
        return client

    @pytest.fixture
    def mock_task_lock(self):
        lock = AsyncMock()
        lock.try_claim.return_value = True
        lock.release.return_value = True
        return lock

    @pytest.mark.asyncio
    async def test_execute_batch(self, mock_mcp_client, mock_task_lock):
        """测试批量执行"""
        pool = ExecutorAgentPool(
            mcp_client=mock_mcp_client,
            task_lock=mock_task_lock,
            pool_size=2,
        )

        tasks = [
            {"id": "task_0", "name": "任务0", "tools": ["web_search"], "depends_on": []},
            {"id": "task_1", "name": "任务1", "tools": ["web_search"], "depends_on": []},
        ]
        context = {"completed_results": {}}

        results = await pool.execute_batch(tasks, context)

        assert len(results) == 2
        assert all(r.success for r in results)
