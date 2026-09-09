"""LangGraph节点实现"""

import json
import asyncio
import structlog
from typing import Literal
from datetime import datetime

from .state import AgentState, TaskStatus
from src.models.task import TaskResult, ExecutionPlan, SubtaskDefinition
from src.agents.planner import ReportPlannerAgent
from src.agents.executor import ExecutorAgent, ExecutorAgentPool
from src.agents.reviewer import ReviewerAgent
from src.tools.mcp_client import MCPClient
from src.tools.registry import MCPToolRegistry
from src.state.redis_lock import RedisTaskLock
from src.config import get_settings
from src.communication.event_bus import EventBus, Event
from src.agent_memory.client import MemoryServiceClient

logger = structlog.get_logger()

# 全局实例（生产环境应使用依赖注入）
_event_bus: EventBus | None = None
_memory_manager: MemoryServiceClient | None = None


def get_llm():
    """获取LLM实例（支持多种提供商）"""
    settings = get_settings()
    
    # 尝试使用langchain-openai
    try:
        from langchain_openai import ChatOpenAI
        llm_kwargs: dict = {}
        if settings.openai_reasoning_effort:
            llm_kwargs["extra_body"] = {
                "reasoning_effort": settings.openai_reasoning_effort,
            }
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0,
            **llm_kwargs,
        )
    except ImportError:
        pass
    
    # 尝试使用langchain-anthropic
    try:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-3-sonnet-20240229",
            api_key=settings.openai_api_key,
            temperature=0,
        )
    except ImportError:
        pass
    
    # 使用默认的FakeLLM（用于测试）
    from langchain_core.language_models import FakeListChatModel
    return FakeListChatModel(responses=["这是一个测试响应"])


def get_event_bus() -> EventBus:
    """获取EventBus单例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def get_memory_manager() -> MemoryServiceClient:
    """获取任务内记忆管理器单例。"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryServiceClient(get_settings().memory_service_url)
    return _memory_manager


async def planner_node(state: AgentState) -> AgentState:
    """Planner节点：分解任务为DAG"""
    settings = get_settings()
    logger.info("planner_node.start", topic=state["topic"])

    # 初始化组件
    llm = get_llm()
    mcp_registry = MCPToolRegistry()
    planner = ReportPlannerAgent(llm=llm, mcp_registry=mcp_registry)

    # 执行规划
    plan = await planner.plan(topic=state["topic"])

    # 初始化子任务状态
    subtasks: dict[str, dict] = {}
    for task_id, task_def in plan.tasks.items():
        subtasks[task_id] = {
            "id": task_id,
            "name": task_def.name,
            "status": TaskStatus.PENDING.value,
            "depends_on": task_def.depends_on,
            "level": plan.get_task_level(task_id),
            "claimed_by": None,
            "result": None,
            "error": None,
            "retry_count": 0,
        }

    # 广播规划完成事件
    event_bus = get_event_bus()
    await event_bus.publish(Event(
        event_type="plan_created",
        task_id=state["task_id"],
        data={
            "total_tasks": plan.metadata.get("total_tasks", 0),
            "levels": len(plan.execution_levels),
            "estimated_time": plan.estimated_time,
        },
        timestamp=datetime.utcnow(),
    ))

    logger.info(
        "planner_node.completed",
        total_tasks=plan.metadata.get("total_tasks"),
        levels=len(plan.execution_levels),
    )

    return {
        **state,
        "plan": plan.model_dump() if hasattr(plan, 'model_dump') else plan.dict(),
        "subtasks": subtasks,
        "execution_levels": plan.execution_levels,
        "current_level": 0,
        "completed_results": {},
        "pending_tasks": plan.execution_levels[0] if plan.execution_levels else [],
        "retry_count": 0,
        "max_retries": settings.max_retries,
        "retry_feedback": {},
        "degraded_tasks": [],
        "current_stage": "planning",
    }


async def level_executor_node(state: AgentState) -> AgentState:
    """按DAG层级执行子任务
    
    关键逻辑：
    1. 只执行当前层级中状态为PENDING或READY的任务
    2. 检查前置依赖是否全部完成
    3. 同一层级的任务并行执行
    """
    settings = get_settings()
    current_level = state["current_level"]
    execution_levels = state["execution_levels"]

    if current_level >= len(execution_levels):
        return {**state, "current_stage": "all_levels_completed"}

    # 获取当前层级的任务ID列表
    current_level_task_ids = execution_levels[current_level]
    subtasks = state["subtasks"]
    completed_results = state["completed_results"]

    logger.info(
        "level_executor_node.start",
        level=current_level,
        tasks=current_level_task_ids,
    )

    # 筛选出可执行的任务（前置依赖全部完成）
    executable_tasks: list[dict] = []
    for task_id in current_level_task_ids:
        task = subtasks[task_id]

        # 检查前置依赖
        deps_completed = all(
            subtasks[dep]["status"] in [TaskStatus.COMPLETED.value, TaskStatus.DEGRADED.value]
            for dep in task["depends_on"]
        )

        if deps_completed and task["status"] in [TaskStatus.PENDING.value, TaskStatus.READY.value]:
            executable_tasks.append(task)

    if not executable_tasks:
        logger.info("level_executor_node.no_executable_tasks", level=current_level)
        return {**state, "current_stage": "level_completed"}

    # 初始化执行组件
    mcp_client = MCPClient(server_configs={
        "web_search": {"url": settings.search_mcp_url},
        "financial_api": {"url": settings.financial_mcp_url},
        "data_cleaner": {"url": settings.cleaner_mcp_url},
        "sentiment_analyzer": {"url": settings.cleaner_mcp_url},
        "chart_generator": {"url": settings.cleaner_mcp_url},
    })
    await mcp_client.initialize()

    task_lock = RedisTaskLock.from_url(settings.redis_url)
    executor_pool = ExecutorAgentPool(
        mcp_client=mcp_client,
        task_lock=task_lock,
        pool_size=3,
    )

    plan_tasks = state.get("plan", {}).get("tasks", {})
    memory_manager = get_memory_manager()

    # 并行执行当前层级的所有可执行任务
    execution_results = await asyncio.gather(
        *[
            executor_pool.execute(
                task={
                    "id": task["id"],
                    "name": task["name"],
                    "description": plan_tasks.get(task["id"], {}).get("description", ""),
                    "tools": plan_tasks.get(task["id"], {}).get("tools", []),
                    "expected_output": plan_tasks.get(task["id"], {}).get("expected_output", "general"),
                    "depends_on": task["depends_on"],
                },
                context={
                    "completed_results": completed_results,
                    "topic": state["topic"],
                    "retry_feedback": state.get("retry_feedback", {}).get(task["id"]),
                },
            )
            for task in executable_tasks
        ],
        return_exceptions=True,
    )

    # 关闭MCP客户端
    await mcp_client.close()

    # 更新子任务状态
    updated_subtasks = {**subtasks}
    updated_completed_results = {**completed_results}
    errors: list[str] = []

    for task, result in zip(executable_tasks, execution_results):
        if isinstance(result, Exception):
            updated_subtasks[task["id"]] = {
                **updated_subtasks[task["id"]],
                "status": TaskStatus.FAILED.value,
                "error": str(result),
            }
            errors.append(f"{task['name']}: {str(result)}")
        elif result.success:
            updated_subtasks[task["id"]] = {
                **updated_subtasks[task["id"]],
                "status": TaskStatus.COMPLETED.value,
                "result": result.data,
                "completed_at": datetime.utcnow().isoformat(),
            }
            updated_completed_results[task["id"]] = result.data
            tool_results = result.data.get("tool_results", {}) if isinstance(result.data, dict) else {}
            for tool_name, raw_result in tool_results.items():
                try:
                    await memory_manager.store_evidence(
                        task_id=state["task_id"],
                        source_task=task["id"],
                        tool_name=tool_name,
                        raw_result=raw_result,
                    )
                except Exception as exc:
                    logger.warning(
                        "memory.evidence_store_failed",
                        task_id=state["task_id"],
                        source_task=task["id"],
                        tool_name=tool_name,
                        error=str(exc),
                    )
        else:
            updated_subtasks[task["id"]] = {
                **updated_subtasks[task["id"]],
                "status": TaskStatus.FAILED.value,
                "error": result.error,
            }
            errors.append(f"{task['name']}: {result.error}")

    # 广播层级执行完成事件
    event_bus = get_event_bus()
    await event_bus.publish(Event(
        event_type="level_executed",
        task_id=state["task_id"],
        data={
            "level": current_level,
            "completed": [t["id"] for t in executable_tasks if updated_subtasks[t["id"]]["status"] == TaskStatus.COMPLETED.value],
            "failed": [t["id"] for t in executable_tasks if updated_subtasks[t["id"]]["status"] == TaskStatus.FAILED.value],
        },
        timestamp=datetime.utcnow(),
    ))

    logger.info(
        "level_executor_node.completed",
        level=current_level,
        completed=len([t for t in executable_tasks if updated_subtasks[t["id"]]["status"] == TaskStatus.COMPLETED.value]),
        failed=len(errors),
    )

    return {
        **state,
        "subtasks": updated_subtasks,
        "completed_results": updated_completed_results,
        "current_stage": "executing",
        "error": "; ".join(errors) if errors else None,
    }


async def level_reviewer_node(state: AgentState) -> AgentState:
    """按层级审核执行结果（含熔断机制）"""
    settings = get_settings()
    current_level = state["current_level"]
    execution_levels = state["execution_levels"]
    subtasks = state["subtasks"]
    retry_count = state["retry_count"]
    max_retries = state["max_retries"]

    current_level_task_ids = execution_levels[current_level]

    logger.info(
        "level_reviewer_node.start",
        level=current_level,
        retry_count=retry_count,
    )

    # 初始化Reviewer
    llm = get_llm()
    reviewer = ReviewerAgent(
        llm=llm,
        quality_threshold=settings.quality_threshold,
        max_retries=max_retries,
        memory_manager=get_memory_manager(),
    )

    review_results: list[dict] = []
    level_passed = True
    failed_tasks: list[str] = []
    updated_subtasks = {**subtasks}
    degraded_tasks = list(state.get("degraded_tasks", []))

    for task_id in current_level_task_ids:
        task = subtasks[task_id]

        # 跳过已完成或已降级的任务
        if task["status"] in [TaskStatus.COMPLETED.value, TaskStatus.DEGRADED.value]:
            continue

        # 构造结果供Reviewer审核
        if task["status"] == TaskStatus.FAILED.value:
            task_result = TaskResult(
                success=False,
                error=task.get("error", "未知错误"),
                task_id=task_id,
            )
        else:
            task_result = TaskResult(
                success=True,
                data=task.get("result"),
                task_id=task_id,
            )

        task_def = state.get("plan", {}).get("tasks", {}).get(task_id, {})
        try:
            review_context = await get_memory_manager().build_reviewer_context(
                task_id=state["task_id"],
                topic=state["topic"],
                task=task_def,
                current_output_summary=(
                    json.dumps(task.get("result"), ensure_ascii=False)[:2000]
                    if task.get("result")
                    else (task.get("error") or "无输出")
                ),
                dependency_results=state.get("completed_results", {}),
            )
        except Exception as exc:
            logger.warning(
                "reviewer.context_build_failed",
                task_id=state["task_id"],
                task_id_reviewed=task_id,
                error=str(exc),
            )
            review_context = None
        if review_context is not None:
            logger.info(
                "reviewer.context_built",
                task_id=state["task_id"],
                reviewed_task_id=task_id,
                tokens_used=review_context.tokens_used,
                token_budget=review_context.token_budget,
                truncated=review_context.truncated,
                top_memories=len(review_context.top_memories),
            )
        review = await reviewer.review(task_result, task_def, retry_count, review_context)
        review_results.append({"task_id": task_id, "review": review.model_dump()})

        if not review.passed:
            level_passed = False
            failed_tasks.append(task_id)
        elif review.degraded:
            # 降级放行，标记为DEGRADED
            updated_subtasks[task_id] = {
                **updated_subtasks[task_id],
                "status": TaskStatus.DEGRADED.value,
            }
            degraded_tasks.append(task_id)

    # 广播审核结果
    event_bus = get_event_bus()
    await event_bus.publish(Event(
        event_type="level_reviewed",
        task_id=state["task_id"],
        data={
            "level": current_level,
            "passed": level_passed,
            "retry_count": retry_count,
            "review_results": review_results,
        },
        timestamp=datetime.utcnow(),
    ))

    # 判断路由决策
    if level_passed or retry_count >= max_retries:
        # 当前层级通过 或 已达最大重试次数
        if current_level + 1 < len(execution_levels):
            # 还有下一层级
            next_level = current_level + 1
            logger.info(
                "level_reviewer_node.next_level",
                current_level=current_level,
                next_level=next_level,
            )
            return {
                **state,
                "current_level": next_level,
                "pending_tasks": execution_levels[next_level],
                "subtasks": updated_subtasks,
                "degraded_tasks": degraded_tasks,
                "review_feedback": {
                    "level": current_level,
                    "passed": level_passed,
                    "results": review_results,
                },
                "retry_feedback": {},
                "retry_count": 0,  # 重置重试计数
                "current_stage": "level_reviewed",
            }
        else:
            # 所有层级完成
            logger.info("level_reviewer_node.all_levels_completed")
            return {
                **state,
                "subtasks": updated_subtasks,
                "degraded_tasks": degraded_tasks,
                "review_feedback": {
                    "level": current_level,
                    "passed": level_passed,
                    "results": review_results,
                },
                "retry_feedback": {},
                "current_stage": "all_levels_completed",
            }
    else:
        # 需要重试当前层级
        # 将失败任务状态重置为PENDING
        for task_id in failed_tasks:
            updated_subtasks[task_id] = {
                **updated_subtasks[task_id],
                "status": TaskStatus.PENDING.value,
                "retry_count": updated_subtasks[task_id]["retry_count"] + 1,
            }

        logger.warning(
            "level_reviewer_node.retry",
            level=current_level,
            failed_tasks=failed_tasks,
            retry_count=retry_count + 1,
        )

        retry_feedback = {
            item["task_id"]: item["review"].get("details", {}).get("review_feedback", {})
            for item in review_results
            if item["task_id"] in failed_tasks
            and item["review"].get("details", {}).get("review_feedback")
        }

        return {
            **state,
            "subtasks": updated_subtasks,
            "degraded_tasks": degraded_tasks,
            "pending_tasks": failed_tasks,
            "retry_count": retry_count + 1,
            "review_feedback": {
                "level": current_level,
                "passed": False,
                "results": review_results,
            },
            "retry_feedback": retry_feedback,
            "current_stage": "retrying",
        }


def route_after_review(state: AgentState) -> Literal["next_level", "retry_level", "aggregate", "failed"]:
    """审核后的路由决策"""
    current_stage = state["current_stage"]

    if current_stage == "all_levels_completed":
        return "aggregate"

    if current_stage == "level_reviewed":
        return "next_level"

    if current_stage == "retrying":
        if state["retry_count"] >= state["max_retries"]:
            # 达到最大重试次数，降级聚合
            return "aggregate"
        return "retry_level"

    return "failed"


async def aggregator_node(state: AgentState) -> AgentState:
    """聚合节点：整合所有层级结果，生成最终研报"""
    logger.info("aggregator_node.start", topic=state["topic"])

    completed_results = state["completed_results"]
    subtasks = state["subtasks"]
    degraded_tasks = list(state.get("degraded_tasks", []))

    # 收集降级任务
    for task_id, task in subtasks.items():
        if task.get("status") == TaskStatus.DEGRADED.value and task_id not in degraded_tasks:
            degraded_tasks.append(task_id)

    # 调用LLM整合研报
    settings = get_settings()
    llm = get_llm()

    # 构建研报大纲
    sections = []
    for task_id in sorted(completed_results.keys()):
        task = subtasks.get(task_id, {})
        sections.append({
            "title": task.get("name", task_id),
            "content": completed_results[task_id],
            "degraded": task_id in degraded_tasks,
        })

    # 调用LLM整合
    prompt = f"""请将以下研究分析结果整合为一份完整的万字深度研报。

研究主题：{state['topic']}

各章节分析结果：
{json.dumps(sections, ensure_ascii=False, indent=2)[:8000]}

要求：
1. 保持逻辑连贯性，各章节自然衔接
2. 数据引用准确，标注来源
3. 如有降级标记的章节，需特别注明可能存在质量问题
4. 输出格式：Markdown
5. 字数要求：10000字以上"""

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content="你是专业的研报撰写专家"),
            HumanMessage(content=prompt),
        ]
        response = await llm.ainvoke(messages)
        report_content = response.content
    except Exception as e:
        logger.error("aggregator_node.llm_error", error=str(e))
        report_content = f"研报生成失败: {str(e)}\n\n原始数据:\n{json.dumps(completed_results, ensure_ascii=False)[:5000]}"

    final_result = {
        "topic": state["topic"],
        "content": report_content,
        "sections": sections,
        "degraded_sections": degraded_tasks,
        "generated_at": datetime.utcnow().isoformat(),
        "word_count": len(report_content),
    }

    # 广播完成事件
    event_bus = get_event_bus()
    await event_bus.publish(Event(
        event_type="report_completed",
        task_id=state["task_id"],
        data={
            "word_count": final_result["word_count"],
            "degraded_sections": degraded_tasks,
        },
        timestamp=datetime.utcnow(),
    ))

    logger.info(
        "aggregator_node.completed",
        word_count=final_result["word_count"],
        degraded_count=len(degraded_tasks),
    )

    return {
        **state,
        "final_result": final_result,
        "degraded_tasks": degraded_tasks,
        "current_stage": "completed",
    }
