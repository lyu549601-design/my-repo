"""分级摘要提取器单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.memory.summarizer import TieredSummarizer


class TestTieredSummarizer:
    """摘要器测试"""

    def test_search_summary_keeps_sources(self):
        """搜索摘要保留来源"""
        raw = {
            "query": "新能源汽车",
            "results": [
                {
                    "title": "2026年市场报告",
                    "snippet": "市场规模预计增长20%",
                    "url": "https://example.com/report",
                    "source": "serpapi",
                }
            ],
            "total": 1,
        }
        summary = TieredSummarizer()._summarize_search(raw)

        assert "市场规模预计增长20%" in summary.summary
        assert summary.sources[0].url == "https://example.com/report"

    def test_financial_summary_extracts_metrics(self):
        """金融数据提取结构化指标"""
        raw = {
            "symbol": "BYD",
            "period": "2025",
            "data": {"revenue": 602315000000, "net_profit": 30041000000},
            "source": "mock",
        }
        summary = TieredSummarizer()._summarize_financial(raw)

        assert len(summary.metrics) == 2
        assert summary.metrics[0].name == "revenue"
        assert summary.metrics[0].value == "602315000000"
        assert summary.metrics[0].year == "2025"

    @pytest.mark.asyncio
    async def test_llm_fallback_keeps_rule_summary(self):
        """LLM 返回异常时回退到规则摘要"""
        llm = AsyncMock()
        llm.ainvoke.side_effect = Exception("LLM失败")
        summarizer = TieredSummarizer(llm=llm)
        raw = {
            "query": "测试",
            "results": [
                {"title": "标题", "snippet": "结论A", "url": "https://x", "source": "mock"}
            ],
        }

        summary = await summarizer.summarize("t1", "task_0", "web_search", raw)

        assert "结论A" in summary.summary
        assert summary.task_id == "t1"
