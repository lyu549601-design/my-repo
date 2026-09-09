"""权限前置过滤 + 混合检索。"""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from .db import RAGDatabase
from .embedder import HashingEmbedder
from .models import RetrievedChunk, UserContext


def chinese_tokenize(text: str) -> list[str]:
    """中文分词，优先 jieba，缺失时回退字符二元组。"""
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
    """先按用户权限过滤，再做 BM25 + 向量加权融合。"""

    def __init__(
        self,
        db: RAGDatabase,
        embedder,
        alpha: float = 0.3,
        top_k: int = 5,
        semantic_expansion: int = 5,
    ):
        self.db = db
        self.embedder = embedder
        self.alpha = alpha
        self.top_k = top_k
        self.semantic_expansion = semantic_expansion

    async def retrieve(
        self,
        user: UserContext,
        query: str,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            return []

        semantic_candidates = await self._semantic_candidates(user, query)
        all_chunks = await self.db.fetch_allowed_chunks(user)
        if not all_chunks:
            return []

        bm25_scores = self._bm25_scores(all_chunks, query)
        top_bm25_ids = sorted(
            bm25_scores,
            key=bm25_scores.get,
            reverse=True,
        )[: self.top_k * self.semantic_expansion]

        candidates: dict[str, RetrievedChunk] = {}
        for chunk in semantic_candidates:
            candidates[chunk.chunk_id] = chunk
        for chunk in all_chunks:
            if chunk.chunk_id in top_bm25_ids:
                candidates[chunk.chunk_id] = chunk

        if not candidates:
            return []

        normalized_bm25 = _minmax_normalize(
            {key: bm25_scores.get(key, 0.0) for key in candidates}
        )
        semantic_by_id = {
            chunk.chunk_id: chunk.score for chunk in semantic_candidates
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

        ranked_ids = sorted(
            final_scores,
            key=final_scores.get,
            reverse=True,
        )[: self.top_k]

        result = [candidates[chunk_id] for chunk_id in ranked_ids]
        for chunk in result:
            chunk.score = final_scores[chunk.chunk_id]
        return result

    async def _semantic_candidates(
        self,
        user: UserContext,
        query: str,
    ) -> list[RetrievedChunk]:
        try:
            query_embedding = await self.embedder.embed_query(query)
            return await self.db.fetch_allowed_semantic_candidates(
                user=user,
                query_embedding=query_embedding,
                limit=self.top_k * self.semantic_expansion,
            )
        except Exception:
            return []

    @staticmethod
    def _bm25_scores(
        chunks: list[RetrievedChunk],
        query: str,
    ) -> dict[str, float]:
        corpus = [chinese_tokenize(chunk.content) for chunk in chunks]
        bm25 = BM25Okapi(corpus)
        query_tokens = chinese_tokenize(query)
        scores = bm25.get_scores(query_tokens)
        return {
            chunk.chunk_id: float(score)
            for chunk, score in zip(chunks, scores)
        }
