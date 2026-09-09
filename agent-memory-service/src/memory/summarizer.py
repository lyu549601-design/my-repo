"""分级摘要提取器：结构化数据走规则，长文本走 LLM。"""

from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.serialization import extract_json_object

from .models import EvidenceSummary, Metric, Source

logger = structlog.get_logger()


class TieredSummarizer:
    """按工具返回结构分级提取证据摘要。"""

    LLM_PROMPT = """请把以下研报工具的原始返回压缩为中文证据摘要。

工具：{tool_name}
原始返回：
{raw_text}

要求：
1. 只保留研究相关的事实、数值、结论和关键限定词。
2. 保留原文标题、URL、来源字段。
3. summary 不超过 300 字。
4. 返回严格 JSON：{{"claims": ["..."], "metrics": [{{"name": "...", "value": "...", "year": "..."}}], "sources": [{{"title": "...", "url": "...", "source": "..."}}], "summary": "..."}}"""

    def __init__(self, llm: BaseChatModel | None = None, max_summary_chars: int = 300):
        self.llm = llm
        self.max_summary_chars = max_summary_chars

    async def summarize(
        self,
        task_id: str,
        source_task: str,
        tool_name: str,
        raw_result: Any,
    ) -> EvidenceSummary:
        raw_text = json.dumps(raw_result, ensure_ascii=False) if not isinstance(raw_result, str) else raw_result

        summary = self._rule_based_summary(tool_name, raw_result)
        if len(raw_text) > 400 and self.llm is not None:
            llm_summary = await self._llm_summary(tool_name, raw_text)
            if llm_summary is not None:
                summary = llm_summary

        summary.task_id = task_id
        summary.source_task = source_task
        return summary

    def _rule_based_summary(self, tool_name: str, raw_result: Any) -> EvidenceSummary:
        if not isinstance(raw_result, dict):
            return EvidenceSummary(claims=[str(raw_result)[:500]], summary=str(raw_result)[:300])

        if tool_name == "web_search":
            return self._summarize_search(raw_result)
        if tool_name == "financial_api":
            return self._summarize_financial(raw_result)
        if tool_name == "data_cleaner":
            return self._summarize_cleaner(raw_result)
        if tool_name == "sentiment_analyzer":
            return self._summarize_sentiment(raw_result)
        if tool_name == "chart_generator":
            return self._summarize_chart(raw_result)
        return self._summarize_generic(raw_result)

    def _summarize_search(self, raw_result: dict[str, Any]) -> EvidenceSummary:
        results = raw_result.get("results") or []
        claims: list[str] = []
        sources: list[Source] = []
        for item in results[:10]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            snippet = str(item.get("snippet") or "")
            if snippet and snippet not in claims:
                claims.append(snippet)
            sources.append(
                Source(
                    title=title,
                    url=str(item.get("url") or ""),
                    source=str(item.get("source") or ""),
                )
            )
        if not claims:
            claims.append(str(raw_result.get("query") or "搜索无有效结果"))
        summary = "；".join(claims)[: self.max_summary_chars]
        return EvidenceSummary(claims=claims, sources=sources, summary=summary)

    def _summarize_financial(self, raw_result: dict[str, Any]) -> EvidenceSummary:
        data = raw_result.get("data") or {}
        metrics: list[Metric] = []
        claims: list[str] = []
        if isinstance(data, dict):
            symbol = str(raw_result.get("symbol") or "")
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    metrics.append(
                        Metric(
                            name=str(key),
                            value=str(value),
                            year=str(raw_result.get("period") or ""),
                        )
                    )
            for metric in metrics:
                claims.append(f"{symbol} {metric.name} = {metric.value}")
        if not claims:
            claims.append(str(raw_result))
        source = Source(
            title=str(raw_result.get("symbol") or ""),
            url="",
            source=str(raw_result.get("source") or ""),
        )
        summary = "；".join(claims)[: self.max_summary_chars]
        return EvidenceSummary(claims=claims, metrics=metrics, sources=[source], summary=summary)

    def _summarize_cleaner(self, raw_result: dict[str, Any]) -> EvidenceSummary:
        cleaned = raw_result.get("cleaned_data")
        claims = [json.dumps(cleaned, ensure_ascii=False)[:500]] if cleaned else []
        summary = "；".join(claims)[: self.max_summary_chars]
        return EvidenceSummary(claims=claims, summary=summary)

    def _summarize_sentiment(self, raw_result: dict[str, Any]) -> EvidenceSummary:
        claims = [
            f"情感{raw_result.get('sentiment')}，得分{raw_result.get('sentiment_score')}",
            f"正面指标{raw_result.get('positive_indicators')}，负面指标{raw_result.get('negative_indicators')}",
        ]
        summary = "；".join(claims)[: self.max_summary_chars]
        return EvidenceSummary(claims=claims, summary=summary)

    def _summarize_chart(self, raw_result: dict[str, Any]) -> EvidenceSummary:
        claims = [f"图表类型：{raw_result.get('chart_type')}，格式：{raw_result.get('format')}"]
        summary = "；".join(claims)[: self.max_summary_chars]
        return EvidenceSummary(claims=claims, summary=summary)

    def _summarize_generic(self, raw_result: dict[str, Any]) -> EvidenceSummary:
        claims = [json.dumps(raw_result, ensure_ascii=False)[:500]]
        summary = "；".join(claims)[: self.max_summary_chars]
        return EvidenceSummary(claims=claims, summary=summary)

    async def _llm_summary(self, tool_name: str, raw_text: str) -> EvidenceSummary | None:
        assert self.llm is not None
        prompt = self.LLM_PROMPT.format(tool_name=tool_name, raw_text=raw_text[:8000])
        try:
            response = await self.llm.ainvoke(
                [
                    SystemMessage(content="你是研报数据摘要专家"),
                    HumanMessage(content=prompt),
                ]
            )
            data = extract_json_object(response.content)
            if not isinstance(data, dict):
                return None
            return EvidenceSummary.model_validate(data)
        except Exception as exc:
            logger.warning("summarizer.llm_fallback", tool=tool_name, error=str(exc))
            return None
