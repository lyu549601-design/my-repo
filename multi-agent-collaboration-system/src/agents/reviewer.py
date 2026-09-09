"""Reviewer Agent - 质量审核与熔断降级"""

import json
import structlog
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from src.models.task import TaskResult, ReviewResult
from src.utils.serialization import extract_json_object
from src.agent_memory.models import ReviewFeedback, ReviewerContext

logger = structlog.get_logger()


class ReviewerAgent:
    """研报场景Reviewer，含真实一致性校验和反馈闭环"""

    LLM_REVIEW_PROMPT = """请评估以下研报子任务的输出质量：

研究主题：{topic}
任务名称：{task_name}
任务描述：{task_description}
预期输出类型：{expected_output}

当前任务输出（摘要）：
{output_summary}

直接依赖任务摘要：
{dependency_summaries}

相关记忆（Top-3）：
{top_memories}

请从以下维度评分（0-1）：
1. 数据准确性：数据来源是否可靠，数值是否合理
2. 逻辑连贯性：分析逻辑是否自洽
3. 信息完整性：是否覆盖任务要求的关键信息
4. 专业深度：分析是否有足够的专业深度
5. 一致性：当前输出是否与依赖任务和相关记忆存在数值矛盾或事实冲突

返回JSON格式：
{{"accuracy": 0.x, "logic": 0.x, "completeness": 0.x, "depth": 0.x, "consistency": 0.x, "conflicts": ["矛盾描述"], "missing_data": ["缺失数据"], "comments": "..."}}"""

    def __init__(
        self,
        llm: BaseChatModel,
        quality_threshold: float = 0.8,
        max_retries: int = 3,
        memory_manager: Any = None,
    ):
        self.llm = llm
        self.quality_threshold = quality_threshold
        self.max_retries = max_retries
        self.memory_manager = memory_manager

    async def review(
        self,
        task_result: TaskResult,
        task: dict[str, Any],
        retry_count: int,
        context: ReviewerContext | None = None,
    ) -> ReviewResult:
        """审核单个任务结果"""
        task_id = task.get("id", "unknown")
        logger.info("reviewer.start", task_id=task_id, retry_count=retry_count)

        # 1. 熔断检查：达到最大重试次数，强制降级放行
        if retry_count >= self.max_retries:
            logger.warning(
                "reviewer.circuit_breaker_triggered",
                task_id=task_id,
                retry_count=retry_count,
                max_retries=self.max_retries,
            )
            return ReviewResult(
                passed=True,  # 降级放行
                score=0.6,    # 低分标记
                degraded=True,
                warning=f"已达到最大重试次数({self.max_retries})，降级放行",
                suggestions=["建议人工审核此部分结果"],
                details={"auto_check": "SKIPPED", "llm_check": "SKIPPED"},
            )

        # 2. 自动化检查
        auto_checks = self._run_auto_checks(task_result, task, context)

        # 3. LLM辅助检查
        llm_check = await self._llm_review(task_result, task, context)

        # 4. 综合评分
        score = self._calculate_score(auto_checks, llm_check)

        # 5. 判断是否通过
        passed = score >= self.quality_threshold

        # 6. 生成建议与结构化反馈
        suggestions = self._generate_suggestions(auto_checks, llm_check, passed)
        result = ReviewResult(
            passed=passed,
            score=score,
            degraded=False,
            warning=None if passed else f"质量评分{score:.2f}未达阈值{self.quality_threshold}",
            suggestions=suggestions,
            details={"auto_check": auto_checks, "llm_check": llm_check},
        )

        if not passed:
            feedback = self._build_feedback(task_id, task, retry_count, result, auto_checks, llm_check)
            result.details["review_feedback"] = feedback.model_dump()
            if self.memory_manager is not None:
                try:
                    await self.memory_manager.store_review_feedback(feedback)
                except Exception as exc:
                    logger.warning("reviewer.feedback_store_failed", task_id=task_id, error=str(exc))

        logger.info(
            "reviewer.completed",
            task_id=task_id,
            passed=passed,
            score=score,
            degraded=result.degraded,
        )

        return result

    def _run_auto_checks(
        self,
        result: TaskResult,
        task: dict[str, Any],
        context: ReviewerContext | None = None,
    ) -> dict[str, float]:
        """自动化检查项"""
        checks: dict[str, float] = {}

        checks["completeness"] = self._check_completeness(result, task)
        checks["format"] = self._check_format(result)
        checks["freshness"] = self._check_data_freshness(result)
        checks["consistency"] = self._check_consistency(result, context)

        return checks

    async def _llm_review(
        self,
        result: TaskResult,
        task: dict[str, Any],
        context: ReviewerContext | None = None,
    ) -> dict[str, Any]:
        """LLM辅助质量检查"""
        output_summary = (
            context.current_output_summary
            if context is not None
            else (json.dumps(result.data, ensure_ascii=False)[:2000] if result.data else "无输出")
        )
        dependency_summaries = (
            "\n".join(
                f"- {item.summary or '；'.join(item.claims)}"
                for item in context.dependency_summaries
            )
            if context is not None
            else "无"
        )
        top_memories = (
            "\n".join(f"- {item.content[:300]}" for item in context.top_memories)
            if context is not None
            else "无"
        )

        prompt = self.LLM_REVIEW_PROMPT.format(
            topic=context.topic if context is not None else "未知",
            task_name=task.get("name", ""),
            task_description=task.get("description", ""),
            expected_output=task.get("expected_output", ""),
            output_summary=output_summary,
            dependency_summaries=dependency_summaries or "无",
            top_memories=top_memories or "无",
        )

        try:
            messages = [
                SystemMessage(content="你是研报质量审核专家"),
                HumanMessage(content=prompt),
            ]
            response = await self.llm.ainvoke(messages)
            return extract_json_object(response.content)
        except Exception as e:
            logger.warning("reviewer.llm_review_fallback", error=str(e))
            return {
                "accuracy": 0.5,
                "logic": 0.5,
                "completeness": 0.5,
                "depth": 0.5,
                "consistency": 0.5,
                "conflicts": [],
                "missing_data": [],
                "comments": f"LLM返回格式异常: {str(e)}",
            }

    def _calculate_score(self, auto_checks: dict[str, float], llm_check: dict[str, Any]) -> float:
        """综合评分"""
        auto_score = sum(auto_checks.values()) / len(auto_checks) if auto_checks else 0.5
        llm_score = (
            llm_check.get("accuracy", 0.5) * 0.25
            + llm_check.get("logic", 0.5) * 0.2
            + llm_check.get("completeness", 0.5) * 0.2
            + llm_check.get("depth", 0.5) * 0.15
            + llm_check.get("consistency", 0.5) * 0.2
        )

        # 自动化检查权重40%，LLM检查权重60%
        return auto_score * 0.4 + llm_score * 0.6

    def _check_completeness(self, result: TaskResult, task: dict[str, Any]) -> float:
        """完整性检查"""
        if not result.data:
            return 0.0
        if result.data.get("expected_output") == task.get("expected_output"):
            return 1.0
        return 0.7

    def _check_format(self, result: TaskResult) -> float:
        """格式检查"""
        if not result.data:
            return 0.0
        if not isinstance(result.data, dict):
            return 0.3
        return 1.0

    def _check_data_freshness(self, result: TaskResult) -> float:
        """数据新鲜度检查"""
        if not result.data:
            return 0.0
        assembled_at = result.data.get("assembled_at")
        if not assembled_at:
            return 0.5
        return 1.0

    def _check_consistency(
        self,
        result: TaskResult,
        context: ReviewerContext | None = None,
    ) -> float:
        """真实一致性检查：比较依赖摘要与当前输出的关键数值。"""
        if context is None or not (context.dependency_summaries or context.top_memories):
            return 0.5
        if not result.data:
            return 0.0

        output_text = json.dumps(result.data, ensure_ascii=False)
        conflicts = self._find_numeric_conflicts(context, output_text)
        return 0.0 if conflicts else 0.8

    def _find_numeric_conflicts(
        self,
        context: ReviewerContext,
        output_text: str,
    ) -> list[str]:
        conflicts: list[str] = []
        for summary in context.dependency_summaries:
            for metric in summary.metrics:
                if metric.name in output_text and metric.value not in output_text:
                    conflicts.append(
                        f"依赖任务 {summary.source_task or '未知'} 的 {metric.name}={metric.value} 与当前输出不一致"
                    )
        return conflicts

    def _generate_suggestions(
        self,
        auto_checks: dict[str, float],
        llm_check: dict[str, Any],
        passed: bool,
    ) -> list[str]:
        """生成改进建议"""
        suggestions: list[str] = []

        if not passed:
            if auto_checks.get("completeness", 1.0) < 0.8:
                suggestions.append("补充缺失的关键数据字段")
            if auto_checks.get("consistency", 1.0) < 0.8:
                suggestions.append("核对与依赖任务和相关记忆的一致性")
            if llm_check.get("accuracy", 1.0) < 0.7:
                suggestions.append("核实数据来源的准确性")
            if llm_check.get("logic", 1.0) < 0.7:
                suggestions.append("优化分析逻辑的连贯性")
            if llm_check.get("depth", 1.0) < 0.7:
                suggestions.append("增加分析深度，补充专业见解")
            for conflict in llm_check.get("conflicts", [])[:3]:
                suggestions.append(f"解决矛盾：{conflict}")
            for missing in llm_check.get("missing_data", [])[:3]:
                suggestions.append(f"补充数据：{missing}")

        return suggestions if suggestions else ["质量达标，无需改进"]

    def _build_feedback(
        self,
        task_id: str,
        task: dict[str, Any],
        retry_count: int,
        result: ReviewResult,
        auto_checks: dict[str, float],
        llm_check: dict[str, Any],
    ) -> ReviewFeedback:
        deductions = [
            name
            for name, score in auto_checks.items()
            if score < self.quality_threshold
        ]
        missing_data = list(llm_check.get("missing_data", []))
        if auto_checks.get("completeness", 1.0) < self.quality_threshold:
            missing_data.append("任务要求的关键数据字段")

        return ReviewFeedback(
            task_id=task_id,
            source_task=task.get("id", "unknown"),
            retry_count=retry_count + 1,
            score=result.score,
            deductions=deductions,
            missing_data=missing_data,
            conflicts=list(llm_check.get("conflicts", [])),
            suggestions=result.suggestions,
        )
