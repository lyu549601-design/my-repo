"""内存版 RAG 存储，用于无 Docker 环境的端到端演示。"""

from __future__ import annotations

import math

from .models import Document, DocumentChunk, RetrievedChunk, UserContext


class MemoryStore:
    """实现与 RAGDatabase 一致的检索接口，数据仅存在于当前进程。"""

    def __init__(self):
        self.documents: dict[str, Document] = {}
        self.chunks: list[DocumentChunk] = []

    async def upsert_document(self, document: Document) -> None:
        self.documents[document.id] = document

    async def insert_chunks(self, chunks: list[DocumentChunk]) -> None:
        self.chunks.extend(chunks)

    async def fetch_allowed_chunks(
        self,
        user: UserContext,
        limit: int | None = None,
    ) -> list[RetrievedChunk]:
        allowed_docs = self._allowed_documents(user)
        result = [
            self._to_retrieved(chunk)
            for chunk in self.chunks
            if chunk.document_id in allowed_docs
        ]
        return result[:limit] if limit else result

    async def fetch_allowed_semantic_candidates(
        self,
        user: UserContext,
        query_embedding: list[float],
        limit: int,
    ) -> list[RetrievedChunk]:
        allowed_docs = self._allowed_documents(user)
        scored: list[RetrievedChunk] = []
        for chunk in self.chunks:
            if chunk.document_id not in allowed_docs or not chunk.embedding:
                continue
            similarity = self._cosine_similarity(query_embedding, chunk.embedding)
            item = self._to_retrieved(chunk, score=similarity)
            scored.append(item)
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    async def delete_document(self, document_id: str) -> None:
        self.documents.pop(document_id, None)
        self.chunks = [
            chunk for chunk in self.chunks if chunk.document_id != document_id
        ]

    def _allowed_documents(self, user: UserContext) -> set[str]:
        allowed: set[str] = set()
        for document_id, document in self.documents.items():
            if document.project_folder_id in user.project_ids:
                allowed.add(document_id)
            if set(document.visible_department_ids) & set(user.department_ids):
                allowed.add(document_id)
        return allowed

    def _to_retrieved(
        self,
        chunk: DocumentChunk,
        score: float = 0.0,
    ) -> RetrievedChunk:
        document = self.documents[chunk.document_id]
        return RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name=document.title,
            page=chunk.page,
            content=chunk.content,
            score=score,
            metadata=chunk.metadata,
        )

    @staticmethod
    def _cosine_similarity(
        left: list[float],
        right: list[float],
    ) -> float:
        if len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        norm_left = math.sqrt(sum(a * a for a in left))
        norm_right = math.sqrt(sum(b * b for b in right))
        if norm_left == 0 or norm_right == 0:
            return 0.0
        return dot / (norm_left * norm_right)
