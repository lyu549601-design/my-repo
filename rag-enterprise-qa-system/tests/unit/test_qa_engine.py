"""问答引擎单元测试。"""

import pytest

from src.rag.models import QAResult, RetrievedChunk, UserContext
from src.rag.qa_engine import QAEngine


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    async def retrieve(self, user, query):
        return self.chunks


class FakeLLM:
    def __init__(self, answer):
        self.answer = answer

    async def complete(self, system_prompt, user_prompt):
        return self.answer


def make_chunk(chunk_id, score):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc_001",
        document_name="市场策略.pdf",
        page=12,
        content="目标市场份额为25%",
        score=score,
    )


class TestQAEngine:
    @pytest.mark.asyncio
    async def test_answer_maps_citations(self):
        engine = QAEngine(
            retriever=FakeRetriever([make_chunk("c1", 0.9)]),
            llm=FakeLLM("根据《市场策略.pdf》第12页，目标为25% [Ref-1]"),
            confidence_threshold=0.65,
        )

        result = await engine.answer(
            UserContext(user_id="u1"),
            "2026年目标是多少？",
        )

        assert result.rejected is False
        assert len(result.citations) == 1
        assert result.citations[0].document_name == "市场策略.pdf"
        assert result.citations[0].page == 12

    @pytest.mark.asyncio
    async def test_low_confidence_rejects(self):
        engine = QAEngine(
            retriever=FakeRetriever([make_chunk("c1", 0.5)]),
            llm=FakeLLM("答案"),
            confidence_threshold=0.65,
        )

        result = await engine.answer(
            UserContext(user_id="u1"),
            "问题",
        )

        assert result.rejected is True
        assert "置信度" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_no_chunks_rejects(self):
        engine = QAEngine(
            retriever=FakeRetriever([]),
            llm=FakeLLM("答案"),
        )

        result = await engine.answer(
            UserContext(user_id="u1"),
            "问题",
        )

        assert result.rejected is True
        assert result.rejection_reason == "无可用检索结果"

    @pytest.mark.asyncio
    async def test_answer_without_refs_rejects(self):
        engine = QAEngine(
            retriever=FakeRetriever([make_chunk("c1", 0.9)]),
            llm=FakeLLM("没有引用"),
        )

        result = await engine.answer(
            UserContext(user_id="u1"),
            "问题",
        )

        assert result.rejected is True
        assert result.rejection_reason == "答案未包含可验证引用"
