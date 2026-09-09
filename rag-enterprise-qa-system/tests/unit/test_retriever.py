"""混合检索单元测试。"""

import pytest

from src.rag.models import RetrievedChunk, UserContext
from src.rag.retriever import HybridRetriever, chinese_tokenize, _minmax_normalize


class FakeDB:
    def __init__(self, chunks, semantic):
        self.chunks = chunks
        self.semantic = semantic
        self.last_user = None

    async def fetch_allowed_chunks(self, user, limit=None):
        self.last_user = user
        return self.chunks

    async def fetch_allowed_semantic_candidates(self, user, query_embedding, limit):
        self.last_user = user
        return self.semantic


class FakeEmbedder:
    async def embed_query(self, text):
        return [0.1, 0.2, 0.3]


def make_chunk(chunk_id, content, score=0.0):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc_001",
        document_name="测试.pdf",
        page=1,
        content=content,
        score=score,
    )


class TestHybridRetriever:
    def test_chinese_tokenize(self):
        assert len(chinese_tokenize("新能源汽车市场份额")) > 1

    def test_minmax_normalize(self):
        normalized = _minmax_normalize({"a": 0.0, "b": 1.0})
        assert normalized["a"] == 0.0
        assert normalized["b"] == 1.0

        equal = _minmax_normalize({"a": 0.5, "b": 0.5})
        assert equal["a"] == 0.5

    @pytest.mark.asyncio
    async def test_retrieve_uses_user_permission_context(self):
        chunks = [
            make_chunk("c1", "新能源汽车市场份额增长"),
            make_chunk("c2", "碳酸锂价格波动"),
        ]
        semantic = [make_chunk("c1", "新能源汽车市场份额增长", score=0.9)]
        db = FakeDB(chunks, semantic)
        retriever = HybridRetriever(db, FakeEmbedder(), top_k=3)
        user = UserContext(
            user_id="u1",
            department_ids=["dept_1"],
            project_ids=["proj_1"],
        )

        result = await retriever.retrieve(user, "新能源汽车市场份额")

        assert db.last_user is user
        assert result[0].chunk_id == "c1"

    @pytest.mark.asyncio
    async def test_retrieve_empty_when_no_allowed_chunks(self):
        db = FakeDB([], [])
        retriever = HybridRetriever(db, FakeEmbedder(), top_k=3)

        result = await retriever.retrieve(
            UserContext(user_id="u1"),
            "查询",
        )

        assert result == []
