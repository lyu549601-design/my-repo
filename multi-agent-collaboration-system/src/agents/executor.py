"""Executor Agent - 任务执行与MCP工具调用"""

import time
import asyncio
import structlog
from typing import Any
from datetime import datetime

from src.models.task import TaskResult, SubtaskDefinition, MCPRequest, MCPResponse, MCPErrorCode
from src.tools.mcp_client import MCPClient, MCPToolError, MCPConnectionError, MCPTimeoutError
from src.state.redis_lock import RedisTaskLock

logger = structlog.get_logger()


class RetryPolicy:
    """重试策略"""

    def __init__(self, max_retries: int = 3, backoff: float = 1.5):
        self.max_retries = max_retries
        self.backoff = backoff


class ExecutorAgent:
    """研报场景Executor，支持DAG层级执行和MCP工具调用"""

    def __init__(
        self,
        agent_id: str,
        mcp_client: MCPClient,
        task_lock: RedisTaskLock,
        retry_policy: RetryPolicy | None = None,
    ):
        self.agent_id = agent_id
        self.mcp_client = mcp_client
        self.task_lock = task_lock
        self.retry_policy = retry_policy or RetryPolicy()

    async def try_claim_task(self, task_id: str) -> bool:
        """尝试认领任务（分布式锁，防并发）"""
        return await self.task_lock.try_claim(task_id, self.agent_id)

    async def release_task(self, task_id: str) -> None:
        """释放任务锁"""
        await self.task_lock.release(task_id, self.agent_id)

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> TaskResult:
        """执行单个子任务"""
        task_id = task["id"]
        start_time = time.time()

        # 1. 尝试认领任务
        claimed = await self.try_claim_task(task_id)
        if not claimed:
            logger.info("executor.task_already_claimed", task_id=task_id, agent_id=self.agent_id)
            return TaskResult(
                success=False,
                error="任务已被其他Worker认领",
                skipped=True,
                task_id=task_id,
                agent_id=self.agent_id,
            )

        try:
            logger.info("executor.task_started", task_id=task_id, agent_id=self.agent_id)

            # 2. 准备执行上下文
            exec_context = {
                **context,
                "task_id": task_id,
                "agent_id": self.agent_id,
                "previous_results": self._collect_dependencies(task, context),
            }

            # 3. 按顺序调用MCP工具链
            results: dict[str, Any] = {}
            for tool_name in task.get("tools", []):
                tool_result = await self._call_mcp_tool(
                    tool_name=tool_name,
                    task=task,
                    context=exec_context,
                    partial_results=results,
                )
                results[tool_name] = tool_result

            # 4. 组装最终结果
            final_result = self._assemble_result(task, results)

            # 5. 验证结果完整性
            if not self._validate_output(final_result, task.get("expected_output", "general")):
                raise ValueError(f"输出不符合预期格式: {task.get('expected_output')}")

            execution_time = time.time() - start_time

            logger.info(
                "executor.task_completed",
                task_id=task_id,
                agent_id=self.agent_id,
                execution_time=execution_time,
            )

            return TaskResult(
                success=True,
                data=final_result,
                task_id=task_id,
                agent_id=self.agent_id,
                execution_time=execution_time,
            )

        except MCPToolError as e:
            logger.error("executor.mcp_error", task_id=task_id, error=str(e))
            return TaskResult(
                success=False,
                error=f"MCP工具调用失败: {e.message}",
                task_id=task_id,
                agent_id=self.agent_id,
                execution_time=time.time() - start_time,
            )
        except Exception as e:
            logger.error("executor.error", task_id=task_id, error=str(e))
            return TaskResult(
                success=False,
                error=str(e),
                task_id=task_id,
                agent_id=self.agent_id,
                execution_time=time.time() - start_time,
            )
        finally:
            # 6. 释放任务锁
            await self.release_task(task_id)

    async def _call_mcp_tool(
        self,
        tool_name: str,
        task: dict[str, Any],
        context: dict[str, Any],
        partial_results: dict[str, Any],
    ) -> dict[str, Any]:
        """调用MCP工具，含异常捕获和重试"""
        for attempt in range(self.retry_policy.max_retries):
            try:
                effective_description = self._apply_retry_feedback(
                    task.get("description", ""),
                    context,
                )
                # 构造MCP请求
                mcp_request = MCPRequest(
                    tool=tool_name,
                    params={
                        "task_description": effective_description,
                        "context": context,
                        "partial_results": partial_results,
                    },
                    timeout=120,
                    request_id=f"{task['id']}_{tool_name}_{attempt}",
                )

                # 调用MCP Server
                response = await self.mcp_client.call(mcp_request)

                # 检查响应状态
                if not response.success:
                    raise MCPToolError(
                        tool=tool_name,
                        error_code=MCPErrorCode.EXECUTION_ERROR,
                        message=response.error_message or "MCP调用失败",
                    )

                return response.result or {}

            except MCPConnectionError as e:
                if attempt == self.retry_policy.max_retries - 1:
                    raise
                logger.warning(
                    "executor.mcp_connection_retry",
                    tool=tool_name,
                    attempt=attempt + 1,
                    error=str(e),
                )
                await asyncio.sleep(self.retry_policy.backoff ** attempt)

            except MCPTimeoutError as e:
                if attempt == self.retry_policy.max_retries - 1:
                    raise
                logger.warning(
                    "executor.mcp_timeout_retry",
                    tool=tool_name,
                    attempt=attempt + 1,
                    error=str(e),
                )
                await asyncio.sleep(self.retry_policy.backoff ** attempt)

        raise MCPToolError(
            tool=tool_name,
            error_code=MCPErrorCode.EXECUTION_ERROR,
            message="所有重试均失败",
        )

    @staticmethod
    def _apply_retry_feedback(description: str, context: dict[str, Any]) -> str:
        """把上一轮审核反馈转换为可执行的补充提示。"""
        feedback = context.get("retry_feedback")
        if not feedback:
            return description
        if not isinstance(feedback, dict):
            return description

        parts = [description]
        missing = feedback.get("missing_data") or []
        conflicts = feedback.get("conflicts") or []
        suggestions = feedback.get("suggestions") or []

        if missing:
            parts.append("上一轮缺失以下数据：" + "；".join(str(item) for item in missing[:5]))
        if conflicts:
            parts.append("上一轮存在以下矛盾：" + "；".join(str(item) for item in conflicts[:5]))
        if suggestions:
            parts.append("上一轮改进建议：" + "；".join(str(item) for item in suggestions[:5]))

        return "\n".join(parts)

    def _collect_dependencies(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """收集前置依赖任务的结果"""
        results: dict[str, Any] = {}
        completed = context.get("completed_results", {})
        for dep_id in task.get("depends_on", []):
            if dep_id in completed:
                results[dep_id] = completed[dep_id]
        return results

    def _assemble_result(self, task: dict[str, Any], tool_results: dict[str, Any]) -> dict[str, Any]:
        """组装工具结果为结构化输出"""
        return {
            "task_id": task["id"],
            "task_name": task.get("name", ""),
            "expected_output": task.get("expected_output", ""),
            "tool_results": tool_results,
            "assembled_at": datetime.utcnow().isoformat(),
        }

    def _validate_output(self, result: dict[str, Any], expected_type: str) -> bool:
        """验证输出是否符合预期格式"""
        validators = {
            "industry_overview": lambda r: "industry_definition" in str(r) or "tool_results" in r,
            "market_data": lambda r: "tool_results" in r,
            "financial_analysis": lambda r: "tool_results" in r,
            "competitor_matrix": lambda r: "tool_results" in r,
            "tech_analysis": lambda r: "tool_results" in r,
            "consumer_insights": lambda r: "tool_results" in r,
            "risk_analysis": lambda r: "tool_results" in r,
            "final_report": lambda r: bool(r.get("tool_results"))
            and any(r["tool_results"].values())
            and len(str(r)) > 100,
            "general": lambda r: "tool_results" in r,
        }

        validator = validators.get(expected_type, validators["general"])
        return validator(result)


class ExecutorAgentPool:
    """Executor Agent池，管理多个并行执行的Agent"""

    def __init__(
        self,
        mcp_client: MCPClient,
        task_lock: RedisTaskLock,
        pool_size: int = 3,
    ):
        self.agents = [
            ExecutorAgent(
                agent_id=f"executor_{i}",
                mcp_client=mcp_client,
                task_lock=task_lock,
            )
            for i in range(pool_size)
        ]

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> TaskResult:
        """从池中选择一个Agent执行任务"""
        # 简单轮询选择Agent
        agent = self.agents[hash(task["id"]) % len(self.agents)]
        return await agent.execute(task, context)

    async def execute_batch(
        self,
        tasks: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[TaskResult]:
        """并行执行一批任务"""
        return await asyncio.gather(
            *[self.execute(task, context) for task in tasks],
            return_exceptions=False,
        )
