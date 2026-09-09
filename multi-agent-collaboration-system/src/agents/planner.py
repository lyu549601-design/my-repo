"""Planner Agent - 任务规划与DAG分解"""

import json
import structlog
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from src.models.task import ExecutionPlan, SubtaskDefinition
from src.tools.registry import MCPToolRegistry
from src.utils.serialization import extract_json_object

logger = structlog.get_logger()


class ReportPlannerAgent:
    """研报场景专用Planner，输出带拓扑层级的DAG"""

    SYSTEM_PROMPT = """你是一个专业的研报任务规划器。

输入：一个研究主题
输出：JSON格式的任务DAG，包含以下字段：
- tasks: 任务列表，每个任务包含 id, name, description, depends_on, tools, expected_output
- execution_levels: 拓扑排序后的执行层级列表

分解原则：
1. 每个子任务应聚焦单一数据维度，便于并行执行
2. 明确标注依赖关系，确保数据流正确
3. 为每个任务指定合适的MCP工具
4. 控制子任务数量在5-8个

可用工具：
- web_search: 网页实时搜索
- financial_api: 金融数据查询（股票、财报）
- data_cleaner: 数据清洗与格式化
- sentiment_analyzer: 舆情分析
- chart_generator: 图表生成

输出格式（严格JSON）：
```json
{
  "tasks": {
    "task_0": {
      "id": "task_0",
      "name": "任务名称",
      "description": "任务描述",
      "depends_on": [],
      "tools": ["web_search"],
      "expected_output": "output_type"
    }
  },
  "execution_levels": [["task_0", "task_1"], ["task_2"]]
}
```"""

    def __init__(self, llm: BaseChatModel, mcp_registry: MCPToolRegistry):
        self.llm = llm
        self.mcp_registry = mcp_registry

    async def plan(self, topic: str, constraints: dict[str, Any] | None = None) -> ExecutionPlan:
        """规划研报任务，生成DAG"""
        logger.info("planner.start", topic=topic)

        # 1. LLM分析主题并生成DAG
        response = await self._generate_plan(topic, constraints or {})

        # 2. 解析JSON响应（兼容```json围栏）
        try:
            dag_data = extract_json_object(response)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("planner.json_parse_error", error=str(e), response=response[:500])
            raise ValueError(f"LLM返回的JSON格式无效: {e}")

        # 3. 验证DAG无环
        if not self._is_dag_valid(dag_data["tasks"]):
            raise ValueError("生成的依赖图存在循环依赖")

        # 4. 计算拓扑层级
        execution_levels = self._topological_sort(dag_data["tasks"])

        # 5. 构建任务定义
        tasks = {}
        for task_id, task_data in dag_data["tasks"].items():
            tasks[task_id] = SubtaskDefinition(
                id=task_id,
                name=task_data["name"],
                description=task_data["description"],
                depends_on=task_data.get("depends_on", []),
                tools=task_data.get("tools", []),
                expected_output=task_data.get("expected_output", "general"),
            )

        # 6. 验证工具可用性
        for task in tasks.values():
            for tool in task.tools:
                if not self.mcp_registry.is_available(tool):
                    logger.warning("planner.tool_unavailable", tool=tool, task=task.id)

        plan = ExecutionPlan(
            topic=topic,
            tasks=tasks,
            execution_levels=execution_levels,
            estimated_time=self._estimate_time(tasks, execution_levels),
            metadata={
                "total_tasks": len(tasks),
                "max_parallelism": max(len(level) for level in execution_levels),
            },
        )

        logger.info(
            "planner.completed",
            total_tasks=plan.metadata["total_tasks"],
            levels=len(execution_levels),
            estimated_time=plan.estimated_time,
        )

        return plan

    async def _generate_plan(self, topic: str, constraints: dict[str, Any]) -> str:
        """调用LLM生成计划"""
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(
                content=f"研究主题：{topic}\n约束条件：{json.dumps(constraints, ensure_ascii=False)}"
            ),
        ]
        response = await self.llm.ainvoke(messages)
        return response.content

    def _topological_sort(self, tasks: dict[str, Any]) -> list[list[str]]:
        """Kahn算法实现拓扑排序，输出按层级分组的任务ID"""
        in_degree: dict[str, int] = {tid: 0 for tid in tasks}
        graph: dict[str, list[str]] = {tid: [] for tid in tasks}

        for tid, task in tasks.items():
            for dep in task.get("depends_on", []):
                graph[dep].append(tid)
                in_degree[tid] += 1

        levels: list[list[str]] = []
        queue = [tid for tid, deg in in_degree.items() if deg == 0]

        while queue:
            levels.append(queue)
            next_queue: list[str] = []
            for tid in queue:
                for neighbor in graph[tid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            queue = next_queue

        # 验证无环
        processed = sum(len(level) for level in levels)
        if processed != len(tasks):
            raise ValueError("依赖图存在循环")

        return levels

    def _is_dag_valid(self, tasks: dict[str, Any]) -> bool:
        """验证DAG有效性"""
        try:
            self._topological_sort(tasks)
            return True
        except ValueError:
            return False

    def _estimate_time(self, tasks: dict[str, SubtaskDefinition], levels: list[list[str]]) -> int:
        """估算总执行时间（秒）"""
        total = 0
        for level in levels:
            max_time = max(self._estimate_task_time(tasks[tid]) for tid in level)
            total += max_time
        return total

    def _estimate_task_time(self, task: SubtaskDefinition) -> int:
        """单任务时间估算"""
        base_time = 120  # 基础2分钟
        tool_time = len(task.tools) * 30
        return base_time + tool_time
