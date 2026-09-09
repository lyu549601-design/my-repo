"""LangGraph状态图定义"""

from langgraph.graph import StateGraph, END
from typing import Literal

from .state import AgentState
from .nodes import (
    planner_node,
    level_executor_node,
    level_reviewer_node,
    aggregator_node,
    route_after_review,
)


def create_report_agent_graph(checkpointer=None) -> StateGraph:
    """创建研报场景的多Agent协作状态图
    
    架构职责边界：
    - LangGraph StateGraph: 驱动内部状态流转、条件路由、重试控制
    - EventBus/WebSocket: 仅作为副产物，用于向前端实时广播任务进度
    - LangGraph Checkpointer: 持久化图状态快照，支持断点续传
    - Redis: 分布式Worker认领子任务时的防并发竞争锁
    """
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("planner", planner_node)
    graph.add_node("level_executor", level_executor_node)
    graph.add_node("level_reviewer", level_reviewer_node)
    graph.add_node("aggregator", aggregator_node)

    # 定义边
    graph.set_entry_point("planner")

    # Planner → Level Executor
    graph.add_edge("planner", "level_executor")

    # Level Executor → Level Reviewer
    graph.add_edge("level_executor", "level_reviewer")

    # Level Reviewer → 条件路由
    graph.add_conditional_edges(
        "level_reviewer",
        route_after_review,
        {
            "next_level": "level_executor",   # 继续下一层级
            "retry_level": "level_executor",  # 当前层级重试
            "aggregate": "aggregator",        # 所有层级完成
            "failed": END,                    # 任务失败
        },
    )

    # Aggregator → END
    graph.add_edge("aggregator", END)

    return graph.compile(checkpointer=checkpointer)
