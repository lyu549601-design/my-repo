"""混合检索：BM25 关键词 + pgvector 语义相似度。"""

from __future__ import annotations

import re
import structlog
from typing import Protocol

from rank_bm25 import BM25Okapi

from .db import MemoryPostgres
from .embedder import Embedder
from .models import MemoryChunk

logger = structlog.get_logger()


def chinese_tokenize(text: str) -> list[str]:
    """中文友好的分词，优先 jieba，缺失时回退到字符二元组。"""
    text = text.lower()
    try:
        import jieba

        return [token for token in jieba.lcut_for_search(text) if token.strip()]
    except ImportError:
        tokens: list[str] = []
        prev_cjk = ""
        for part in re.findall(r"[\u4e00-\u9fff]|[a-z0-9]+", text):
            if re.fullmatch(r"[\u4e00-\u9fff]", part):
                if prev_cjk:
                    tokens.append(prev_cjk + part)
                prev_cjk = part
                tokens.append(part)
            else:
                prev_cjk = ""
                tokens.append(part)
        return tokens


def _minmax_normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    minimum, maximum = min(values), max(values)
    if maximum == minimum:
        return {key: 0.5 for key in scores}
    return {
        key: (value - minimum) / (maximum - minimum)
        for key, value in scores.items()
    }


class HybridRetriever:
    """任务内混合检索器。"""

    def __init__(
        self,
        db: MemoryPostgres,
        embedder: Embedder,
        alpha: float = 0.3,
        top_k: int = 3,
        semantic_expansion: int = 5,
    ):
        self.db = db
        self.embedder = embedder
        self.alpha = alpha
        self.top_k = top_k
        self.semantic_expansion = semantic_expansion

    async def retrieve(self, task_id: str, query: str) -> list[MemoryChunk]:
        if not query.strip():
            return []

        semantic_candidates = await self._semantic_candidates(task_id, query)
        all_chunks = await self.db.fetch_chunks(task_id, chunk_type="evidence_summary")
        if not all_chunks:
            return []

        bm25_scores = self._bm25_scores(all_chunks, query)
        top_bm25 = sorted(bm25_scores, key=bm25_scores.get, reverse=True)[
            : self.top_k * self.semantic_expansion
        ]

        candidates: dict[str, MemoryChunk] = {}
        for chunk in semantic_candidates:
            candidates[chunk.id or ""] = chunk
        for chunk_id in top_bm25:
            chunk = next((c for c in all_chunks if c.id == chunk_id), None)
            if chunk:
                candidates[chunk.id or ""] = chunk

        if not candidates:
            return []

        normalized_bm25 = _minmax_normalize(
            {key: bm25_scores.get(key, 0.0) for key in candidates}
        )
        semantic_by_id = {
            chunk.id: chunk.semantic_similarity or 0.0
            for chunk in semantic_candidates
        }
        normalized_semantic = _minmax_normalize(
            {key: semantic_by_id.get(key, 0.0) for key in candidates}
        )

        final_scores: dict[str, float] = {}
        for chunk_id in candidates:
            final_scores[chunk_id] = (
                self.alpha * normalized_bm25.get(chunk_id, 0.0)
                + (1.0 - self.alpha) * normalized_semantic.get(chunk_id, 0.0)
            )

        ranked_ids = sorted(final_scores, key=final_scores.get, reverse=True)[: self.top_k]
        selected = [candidates[chunk_id] for chunk_id in ranked_ids if candidates.get(chunk_id)]

        try:
            await self.db.increment_access([chunk.id for chunk in selected if chunk.id])
        except Exception as exc:
            logger.warning("retriever.access_update_failed", error=str(exc))

        return selected

    async def _semantic_candidates(
        self,
        task_id: str,
        query: str,
    ) -> list[MemoryChunk]:
        try:
            query_embedding = await self.embedder.embed_query(query)
            chunks = await self.db.fetch_semantic_candidates(
                task_id,
                query_embedding,
                limit=self.top_k * self.semantic_expansion,
            )
            return chunks
        except Exception as exc:
            logger.warning("retriever.semantic_fallback", error=str(exc))
            return []

    @staticmethod
    def _bm25_scores(chunks: list[MemoryChunk], query: str) -> dict[str, float]:
        corpus = [chinese_tokenize(chunk.content) for chunk in chunks]
        bm25 = BM25Okapi(corpus)
        query_tokens = chinese_tokenize(query)
        scores = bm25.get_scores(query_tokens)
        return {
            chunk.id: float(score)
            for chunk, score in zip(chunks, scores)
            if chunk.id
        }
