"""MemoryManager 单元测试"""

import pytest

from src.memory.manager import MemoryManager
from src.memory.models import MemoryChunk, ReviewFeedback
from src.memory.summarizer import TieredSummarizer


class FakeDB:
    def __init__(self):
        self.deleted_tasks = []
        self.chunks = []

    async def upsert_chunk(self, chunk):
        self.chunks.append(chunk)
        return chunk

    async def delete_task(self, task_id):
        self.deleted_tasks.append(task_id)

    async def fetch_feedback(self, task_id, source_task, retry_count):
        return None

    async def fetch_chunks(self, task_id, chunk_type=None, source_task=None):
        return []


class FakeRedis:
    def __init__(self, keys=None):
        self.keys = keys or ["memory:t1:evidence:task_0", "memory:t1:feedback:task_0:1"]
        self.deleted = []
        self.store = {}

    async def scan_iter(self, match="", count=100):
        for key in self.keys:
            if key.startswith(match.rstrip("*")):
                yield key

    async def delete(self, *keys):
        self.deleted.extend(keys)

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value
        return True


class FakeRetriever:
    async def retrieve(self, task_id, query):
        return [
            MemoryChunk(
                id="m1",
                task_id=task_id,
                source_task="task_0",
                content="这是一段很长很长的相关记忆内容" * 30,
            )
        ]


class FakeEmbedder:
    async def embed_query(self, text):
        return [0.1, 0.2]


class TestMemoryManager:
    @pytest.mark.asyncio
    async def test_build_reviewer_context_applies_budget(self):
        manager = MemoryManager(
            db=FakeDB(),
            redis_client=FakeRedis(),
            retriever=FakeRetriever(),
            summarizer=TieredSummarizer(),
            embedder=FakeEmbedder(),
            token_budget=100,
        )

        context = await manager.build_reviewer_context(
            task_id="t1",
            topic="2026年新能源汽车",
            task={"description": "市场规模", "depends_on": []},
            current_output_summary="当前任务输出摘要" * 20,
        )

        assert context.tokens_used <= context.token_budget
        assert context.truncated is True

    @pytest.mark.asyncio
    async def test_clear_task_removes_redis_and_db(self):
        db = FakeDB()
        redis = FakeRedis()
        manager = MemoryManager(
            db=db,
            redis_client=redis,
            retriever=FakeRetriever(),
            summarizer=TieredSummarizer(),
            embedder=FakeEmbedder(),
        )

        await manager.clear_task("t1")

        assert db.deleted_tasks == ["t1"]
        assert "memory:t1:evidence:task_0" in redis.deleted
        assert "memory:t1:feedback:task_0:1" in redis.deleted

    def test_summary_to_text_contains_metrics_and_sources(self):
        from src.memory.models import EvidenceSummary, Metric, Source

        summary = EvidenceSummary(
            summary="摘要",
            claims=["结论"],
            metrics=[Metric(name="revenue", value="100", unit="亿")],
            sources=[Source(title="来源", url="https://x", source="mock")],
        )

        text = MemoryManager._summary_to_text(summary)

        assert "revenue=100亿" in text
        assert "https://x" in text

    @pytest.mark.asyncio
    async def test_feedback_round_trip_via_redis(self):
        redis = FakeRedis(keys=[])
        manager = MemoryManager(
            db=FakeDB(),
            redis_client=redis,
            retriever=FakeRetriever(),
            summarizer=TieredSummarizer(),
            embedder=FakeEmbedder(),
        )
        feedback = ReviewFeedback(
            task_id="t1",
            source_task="task_0",
            retry_count=1,
            score=0.5,
            deductions=["consistency"],
            missing_data=["市场份额"],
            conflicts=["规模矛盾"],
            suggestions=["补充数据"],
        )

        await manager.store_review_feedback(feedback)

        loaded = await manager.get_retry_feedback("t1", "task_0", 1)
        assert loaded is not None
        assert loaded.missing_data == ["市场份额"]
        assert loaded.conflicts == ["规模矛盾"]
