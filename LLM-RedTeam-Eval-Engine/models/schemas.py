from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class AttackStrategy(str, Enum):
    """红队攻击策略枚举。"""

    DAN = "DAN"
    ROLEPLAY = "Roleplay"
    ENCODING_BYPASS = "EncodingBypass"
    PROMPT_INJECTION = "PromptInjection"
    CONTEXT_MANIPULATION = "ContextManipulation"


class SafetyCategory(str, Enum):
    """安全评测分类枚举。"""

    HATE = "hate"
    VIOLENCE = "violence"
    SEXUAL = "sexual"
    SELF_HARM = "self_harm"
    ILLEGAL_ACTIVITY = "illegal_activity"
    PII_LEAK = "pii_leak"
    BIAS = "bias"
    MISINFORMATION = "misinformation"


class TestCase(BaseModel):
    """单条安全评测用例。

    描述一个待测安全场景，包含分类与原始提示词。
    """

    id: str = Field(..., description="测试用例唯一标识")
    category: SafetyCategory = Field(..., description="安全评测分类，如 hate / violence 等")
    original_prompt: str = Field(..., description="原始提示词，即未经过变异的基准输入")


class AttackPayload(BaseModel):
    """一条红队攻击载荷。

    由攻击载荷生成器对 TestCase 的 original_prompt 进行策略变异后产出。
    """

    id: str = Field(..., description="攻击载荷唯一标识")
    test_case_id: str = Field(..., description="所属测试用例 ID，建立与 TestCase 的关联")
    mutated_prompt: str = Field(..., description="经过攻击策略变异后的提示词")
    attack_strategy: AttackStrategy = Field(..., description="使用的攻击策略类型")


class EvalResult(BaseModel):
    """单条评测结果。

    记录目标模型对某条 AttackPayload 的回复以及多位裁判的打分情况。
    """

    id: str = Field(..., description="评测结果唯一标识")
    payload_id: str = Field(..., description="关联的攻击载荷 ID")
    target_model_response: str = Field(..., description="目标模型对变异提示词的原始回复内容")
    judge_scores: List[int] = Field(
        default_factory=list,
        description="各裁判的打分列表，每个元素为一位裁判给出的 0-10 分",
    )
    final_score: float = Field(
        default=0.0,
        description="最终综合得分，通常为 judge_scores 的加权或平均值",
    )
    is_violation: bool = Field(
        default=False,
        description="是否判定为安全违规：True 表示模型回复违反了安全策略",
    )
