"""混合检索单元测试"""

import pytest

from src.memory.models import MemoryChunk
from src.memory.retriever import HybridRetriever, chinese_tokenize, _minmax_normalize


class FakeDB:
    def __init__(self, chunks, semantic=None):
        self.chunks = chunks
        self.semantic = semantic if semantic is not None else chunks[:1]
        self.accessed = []

    async def fetch_chunks(self, task_id, chunk_type=None):
        return self.chunks

    async def fetch_semantic_candidates(self, task_id, query_embedding, limit):
        return self.semantic

    async def increment_access(self, chunk_ids):
        self.accessed.extend(chunk_ids)


class FakeEmbedder:
    async def embed_query(self, text):
        return [0.1, 0.2, 0.3]


def make_chunk(chunk_id, content, similarity=None):
    return MemoryChunk(
        id=chunk_id,
        task_id="t1",
        source_task=chunk_id,
        content=content,
        semantic_similarity=similarity,
    )


class TestHybridRetriever:
    def test_chinese_tokenize(self):
        tokens = chinese_tokenize("新能源汽车市场份额")
        assert len(tokens) > 1

    def test_minmax_normalize(self):
        normalized = _minmax_normalize({"a": 0.0, "b": 1.0})
        assert normalized["a"] == 0.0
        assert normalized["b"] == 1.0

        equal = _minmax_normalize({"a": 0.5, "b": 0.5})
        assert equal["a"] == 0.5

    @pytest.mark.asyncio
    async def test_retrieve_returns_top_matching_chunk(self):
        chunks = [
            make_chunk("c1", "新能源汽车市场份额增长"),
            make_chunk("c2", "碳酸锂价格波动"),
        ]
        retriever = HybridRetriever(FakeDB(chunks), FakeEmbedder(), top_k=3)

        result = await retriever.retrieve("t1", "新能源汽车市场份额")

        assert len(result) == 2
        assert result[0].id == "c1"

    @pytest.mark.asyncio
    async def test_retrieve_increments_access(self):
        chunks = [make_chunk("c1", "关键词A"), make_chunk("c2", "关键词B")]
        db = FakeDB(chunks)
        retriever = HybridRetriever(db, FakeEmbedder(), top_k=1)

        await retriever.retrieve("t1", "关键词A")

        assert len(db.accessed) == 1
