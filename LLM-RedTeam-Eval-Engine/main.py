"""LLM-RedTeam-Eval-Engine FastAPI 入口。

提供单接口的红队安全评测服务：
    POST /api/v1/run_evaluation
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from core.async_client import AsyncLLMClient, LLMClientError
from core.config import get_settings
from core.evaluator import MultiJudgeEvaluator
from core.red_team import RedTeamGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LLM-RedTeam-Eval-Engine",
    description="大模型安全红队与自动化评测引擎",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------

class EvalRequest(BaseModel):
    """评测请求体。"""

    original_prompt: str = Field(
        ...,
        min_length=1,
        description="待评测的原始提示词（如：如何制造炸弹）",
        json_schema_extra={"example": "如何制造炸弹"},
    )
    target_model: str = Field(
        ...,
        min_length=1,
        description="目标被测模型名称（如：gpt-4o、deepseek-chat）",
        json_schema_extra={"example": "qwen-plus"},
    )
    num_variants: int = Field(
        default=2,
        ge=1,
        le=10,
        description="红队变异提示词数量，范围 1-10",
    )
    judge_models: Optional[List[str]] = Field(
        default=None,
        description="裁判模型列表，为空时使用配置默认值",
        json_schema_extra={"example": ["qwen-plus", "qwen-plus"]},
    )


class MutationRecord(BaseModel):
    """单条变异及对应的模型回复记录。"""

    mutated_prompt: str = Field(..., description="变异后的提示词")
    model_response: str = Field(default="", description="目标模型的回复内容")
    eval_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="该条回复的多裁判评估结果",
    )


class EvalResponse(BaseModel):
    """评测响应体。"""

    request_id: str = Field(..., description="本次评测的唯一请求 ID")
    original_prompt: str = Field(..., description="原始提示词")
    target_model: str = Field(..., description="被测模型名称")
    total_time_seconds: float = Field(..., description="评测总耗时（秒）")
    mutations: List[MutationRecord] = Field(
        default_factory=list,
        description="所有变异条目的完整评测记录",
    )
    aggregate: Dict[str, Any] = Field(
        default_factory=dict,
        description="聚合统计：平均分、违规率等",
    )


# ---------------------------------------------------------------------------
# 核心业务逻辑
# ---------------------------------------------------------------------------

async def _run_evaluation_pipeline(
    original_prompt: str,
    target_model: str,
    num_variants: int,
    judge_models: Optional[List[str]],
) -> EvalResponse:
    """执行完整的评测流水线。

    流程：变异生成 → 并发模型调用 → 并发多裁判评估 → 聚合结果。

    Args:
        original_prompt: 原始提示词。
        target_model: 目标被测模型。
        num_variants: 变异数量。
        judge_models: 裁判模型列表。

    Returns:
        完整的评测响应体。

    Raises:
        HTTPException: 各阶段可恢复的业务异常。
    """
    request_id = str(uuid.uuid4())
    t_start = time.perf_counter()
    logger.info("[%s] 评测开始 | prompt=%.80s model=%s variants=%d", request_id, original_prompt, target_model, num_variants)

    async with AsyncLLMClient() as client:
        # ── 阶段 A：红队变异生成 ──────────────────────────────────────────
        logger.info("[%s] 阶段A：生成红队变异提示词...", request_id)
        generator = RedTeamGenerator(client=client)
        try:
            mutated_prompts = await generator.generate_mutations(
                base_prompt=original_prompt,
                num_variants=num_variants,
                model=target_model,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"红队变异生成失败: {exc}",
            ) from exc

        if not mutated_prompts:
            raise HTTPException(
                status_code=502,
                detail="红队变异生成返回空列表，无法继续评测",
            )

        logger.info("[%s] 阶段A完成：生成 %d 条变异", request_id, len(mutated_prompts))

        # ── 阶段 B：并发调用目标模型回答 ──────────────────────────────────
        logger.info("[%s] 阶段B：并发调用目标模型...", request_id)

        async def _call_target(prompt: str) -> str:
            """调用目标模型获取回复。"""
            messages = [{"role": "user", "content": prompt}]
            return await client.call_llm(
                messages=messages,
                model=target_model,
                temperature=0.7,
            )

        try:
            responses: List[str] = await asyncio.gather(
                *[_call_target(p) for p in mutated_prompts],
            )
        except LLMClientError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"目标模型调用失败: {exc}",
            ) from exc

        logger.info("[%s] 阶段B完成：收到 %d 条回复", request_id, len(responses))

        # ── 阶段 C：并发多裁判评估 ────────────────────────────────────────
        logger.info("[%s] 阶段C：并发多裁判评估...", request_id)
        evaluator = MultiJudgeEvaluator(client=client)

        eval_tasks = [
            evaluator.evaluate_response(
                question=original_prompt,
                response=resp,
                judge_models=judge_models,
            )
            for resp in responses
        ]

        try:
            eval_results: List[Dict[str, Any]] = await asyncio.gather(*eval_tasks)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"裁判评估阶段异常: {exc}",
            ) from exc

        logger.info("[%s] 阶段C完成", request_id)

    # ── 阶段 D：组装结果 ──────────────────────────────────────────────────
    mutations: List[MutationRecord] = []
    all_scores: List[int] = []
    violation_count = 0

    for prompt, resp, er in zip(mutated_prompts, responses, eval_results):
        mutations.append(MutationRecord(
            mutated_prompt=prompt,
            model_response=resp,
            eval_result=er,
        ))
        all_scores.extend(er.get("scores", []))
        if er.get("is_violation", False):
            violation_count += 1

    total_time = round(time.perf_counter() - t_start, 3)

    aggregate = {
        "total_mutations": len(mutated_prompts),
        "violation_count": violation_count,
        "violation_rate": round(violation_count / len(mutated_prompts), 4) if mutated_prompts else 0.0,
        "avg_score": round(sum(all_scores) / len(all_scores), 4) if all_scores else 0.0,
        "total_judge_scores": len(all_scores),
    }

    logger.info(
        "[%s] 评测完成 | 耗时=%.2fs 违规=%d/%d 平均分=%.2f",
        request_id,
        total_time,
        violation_count,
        len(mutated_prompts),
        aggregate["avg_score"],
    )

    return EvalResponse(
        request_id=request_id,
        original_prompt=original_prompt,
        target_model=target_model,
        total_time_seconds=total_time,
        mutations=mutations,
        aggregate=aggregate,
    )


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@app.post(
    "/api/v1/run_evaluation",
    response_model=EvalResponse,
    summary="执行红队安全评测",
    description="对指定提示词进行红队变异、模型调用、多裁判评估的完整评测流程。",
    tags=["evaluation"],
)
async def run_evaluation(request: EvalRequest) -> EvalResponse:
    """POST /api/v1/run_evaluation

    接收评测请求，执行完整的红队安全评测流水线：
    1. 红队变异生成（LLM-as-an-Attacker）
    2. 并发调用目标模型获取回复
    3. 并发多裁判安全评估（LLM-as-a-Judge）
    4. 聚合结果并返回

    Args:
        request: 评测请求体。

    Returns:
        包含完整评测流转信息的 JSON 响应。

    Raises:
        422: 请求参数校验失败。
        502: 红队变异或目标模型调用失败。
        500: 裁判评估阶段内部错误。
    """
    return await _run_evaluation_pipeline(
        original_prompt=request.original_prompt,
        target_model=request.target_model,
        num_variants=request.num_variants,
        judge_models=request.judge_models,
    )


@app.get("/health", tags=["system"])
async def health_check() -> Dict[str, str]:
    """健康检查端点。"""
    return {"status": "ok"}
