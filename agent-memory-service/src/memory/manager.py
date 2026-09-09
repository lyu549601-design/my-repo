"""任务内记忆管理器。"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
import structlog

from src.config import Settings, get_settings

from .db import MemoryPostgres
from .embedder import Embedder, LocalEmbedder, OpenAIEmbedder
from .models import (
    EvidenceSummary,
    MemoryChunk,
    ReviewFeedback,
    ReviewerContext,
)
from .retriever import HybridRetriever
from .summarizer import TieredSummarizer

logger = structlog.get_logger()


class MemoryManager:
    """短期 Redis + 长期 pgvector 的统一入口。"""

    def __init__(
        self,
        db: MemoryPostgres,
        redis_client: aioredis.Redis,
        retriever: HybridRetriever,
        summarizer: TieredSummarizer,
        embedder: Embedder,
        token_budget: int = 1600,
        ttl_seconds: int = 7200,
    ):
        self.db = db
        self.redis = redis_client
        self.retriever = retriever
        self.summarizer = summarizer
        self.embedder = embedder
        self.token_budget = token_budget
        self.ttl_seconds = ttl_seconds

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        summarizer_llm: Any = None,
    ) -> "MemoryManager":
        settings = settings or get_settings()
        db = MemoryPostgres(settings.postgres_url)
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        if settings.embedding_provider == "local":
            embedder = LocalEmbedder(settings.embedding_model, settings.embedding_dim)
        else:
            embedder = OpenAIEmbedder(settings)
        retriever = HybridRetriever(
            db=db,
            embedder=embedder,
            alpha=settings.memory_bm25_weight,
            top_k=settings.memory_retrieval_top_k,
        )
        summarizer = TieredSummarizer(llm=summarizer_llm)
        return cls(
            db=db,
            redis_client=redis_client,
            retriever=retriever,
            summarizer=summarizer,
            embedder=embedder,
            token_budget=settings.memory_token_budget,
            ttl_seconds=settings.memory_ttl_seconds,
        )

    async def store_evidence(
        self,
        task_id: str,
        source_task: str,
        tool_name: str,
        raw_result: Any,
        importance: float = 0.5,
    ) -> EvidenceSummary:
        summary = await self.summarizer.summarize(
            task_id=task_id,
            source_task=source_task,
            tool_name=tool_name,
            raw_result=raw_result,
        )
        content = self._summary_to_text(summary)
        embeddings = await self.embedder.embed_texts([content])
        chunk = MemoryChunk(
            task_id=task_id,
            source_task=source_task,
            chunk_type="evidence_summary",
            content=content,
            embedding=embeddings[0] if embeddings else None,
            importance=importance,
            metadata={"summary_json": summary.model_dump_json()},
        )
        await self.db.upsert_chunk(chunk)
        await self.redis.set(
            self._evidence_key(task_id, source_task),
            summary.model_dump_json(),
            ex=self.ttl_seconds,
        )
        logger.info(
            "memory.evidence_stored",
            task_id=task_id,
            source_task=source_task,
            tool_name=tool_name,
        )
        return summary

    async def store_review_feedback(self, feedback: ReviewFeedback) -> None:
        chunk = MemoryChunk(
            task_id=feedback.task_id,
            source_task=feedback.source_task,
            chunk_type="review_feedback",
            content=feedback.model_dump_json(),
            metadata={"retry_count": feedback.retry_count},
        )
        await self.db.upsert_chunk(chunk)
        await self.redis.set(
            self._feedback_key(
                feedback.task_id,
                feedback.source_task,
                feedback.retry_count,
            ),
            feedback.model_dump_json(),
            ex=self.ttl_seconds,
        )
        logger.info(
            "memory.feedback_stored",
            task_id=feedback.task_id,
            source_task=feedback.source_task,
            retry_count=feedback.retry_count,
        )

    async def get_retry_feedback(
        self,
        task_id: str,
        source_task: str,
        retry_count: int,
    ) -> ReviewFeedback | None:
        redis_key = self._feedback_key(task_id, source_task, retry_count)
        cached = await self.redis.get(redis_key)
        if cached:
            return ReviewFeedback.model_validate_json(cached)
        chunk = await self.db.fetch_feedback(task_id, source_task, retry_count)
        if not chunk:
            return None
        feedback = ReviewFeedback.model_validate_json(chunk.content)
        await self.redis.set(redis_key, chunk.content, ex=self.ttl_seconds)
        return feedback

    async def get_evidence_summary(
        self,
        task_id: str,
        source_task: str,
    ) -> EvidenceSummary | None:
        redis_key = self._evidence_key(task_id, source_task)
        cached = await self.redis.get(redis_key)
        if cached:
            return EvidenceSummary.model_validate_json(cached)
        chunks = await self.db.fetch_chunks(
            task_id,
            chunk_type="evidence_summary",
            source_task=source_task,
        )
        if not chunks:
            return None
        summary_json = chunks[0].metadata.get("summary_json")
        if not summary_json:
            return None
        summary = EvidenceSummary.model_validate_json(summary_json)
        await self.redis.set(redis_key, summary.model_dump_json(), ex=self.ttl_seconds)
        return summary

    async def build_reviewer_context(
        self,
        task_id: str,
        topic: str,
        task: dict[str, Any],
        current_output_summary: str,
        dependency_results: dict[str, Any] | None = None,
        token_budget: int | None = None,
    ) -> ReviewerContext:
        budget = token_budget or self.token_budget
        task_description = task.get("description", "")
        query = f"{topic} {task_description}"
        top_memories = await self.retriever.retrieve(task_id, query)

        dependency_summaries: list[EvidenceSummary] = []
        for dep_id in task.get("depends_on", []):
            stored = await self.get_evidence_summary(task_id, dep_id)
            if stored is not None:
                dependency_summaries.append(stored)
            elif dependency_results and dep_id in dependency_results:
                fallback = await self.summarizer.summarize(
                    task_id=task_id,
                    source_task=dep_id,
                    tool_name="general",
                    raw_result=dependency_results[dep_id],
                )
                dependency_summaries.append(fallback)

        context = ReviewerContext(
            task_id=task_id,
            topic=topic,
            task_name=task.get("name", ""),
            task_description=task_description,
            expected_output=task.get("expected_output", "general"),
            current_output_summary=current_output_summary,
            dependency_summaries=dependency_summaries,
            top_memories=top_memories,
            token_budget=budget,
        )
        return self._apply_token_budget(context)

    async def clear_task(self, task_id: str) -> None:
        await self.db.delete_task(task_id)
        async for key in self.redis.scan_iter(match=f"memory:{task_id}:*", count=100):
            await self.redis.delete(key)
        logger.info("memory.task_cleared", task_id=task_id)

    async def close(self) -> None:
        await self.db.close()
        await self.redis.aclose()

    @staticmethod
    def _summary_to_text(summary: EvidenceSummary) -> str:
        parts = [summary.summary, *summary.claims]
        metrics_text = "；".join(
            f"{metric.name}={metric.value}{metric.unit or ''}"
            + (f"({metric.year})" if metric.year else "")
            for metric in summary.metrics
        )
        if metrics_text:
            parts.append(metrics_text)
        sources_text = "；".join(
            f"{source.title} {source.url} [{source.source}]"
            for source in summary.sources
            if source.title or source.url
        )
        if sources_text:
            parts.append(sources_text)
        return "\n".join(part for part in parts if part)

    def _apply_token_budget(
        self,
        context: ReviewerContext,
    ) -> ReviewerContext:
        budget = context.token_budget
        tokens_used = 0
        truncated = False

        def fit(text: str) -> str:
            nonlocal tokens_used, truncated
            remaining = max(budget - tokens_used, 0)
            if len(text) <= remaining:
                tokens_used += len(text)
                return text
            truncated = True
            clipped = text[:remaining]
            tokens_used += len(clipped)
            return clipped

        context.topic = fit(context.topic)
        context.task_name = fit(context.task_name)
        context.task_description = fit(context.task_description)
        context.current_output_summary = fit(context.current_output_summary)

        kept_deps: list[EvidenceSummary] = []
        for summary in context.dependency_summaries:
            summary.summary = fit(summary.summary)
            if summary.summary:
                kept_deps.append(summary)
        context.dependency_summaries = kept_deps

        kept_memories: list[MemoryChunk] = []
        for chunk in context.top_memories:
            chunk.content = fit(chunk.content)
            if chunk.content:
                kept_memories.append(chunk)
        context.top_memories = kept_memories

        context.tokens_used = tokens_used
        context.truncated = truncated
        return context

    @staticmethod
    def _evidence_key(task_id: str, source_task: str) -> str:
        return f"memory:{task_id}:evidence:{source_task}"

    @staticmethod
    def _feedback_key(task_id: str, source_task: str, retry_count: int) -> str:
        return f"memory:{task_id}:feedback:{source_task}:{retry_count}"
