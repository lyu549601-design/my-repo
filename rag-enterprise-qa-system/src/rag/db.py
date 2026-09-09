"""RAG 系统 PostgreSQL + pgvector 存取层。"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import asyncpg

from .models import Document, DocumentChunk, RetrievedChunk, UserContext


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


class RAGDatabase:
    """文档、切片、权限过滤与语义检索。"""

    SCHEMA_SQL = """
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        file_path TEXT,
        file_type TEXT,
        page_count INTEGER DEFAULT 0,
        project_folder_id TEXT,
        visible_department_ids TEXT[] NOT NULL DEFAULT '{}',
        visible_role_ids TEXT[] NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'ready',
        uploaded_by TEXT,
        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS document_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        page INTEGER NOT NULL DEFAULT 1,
        chapter TEXT,
        start_offset INTEGER DEFAULT 0,
        end_offset INTEGER DEFAULT 0,
        content TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        embedding vector(512),
        metadata JSONB NOT NULL DEFAULT '{}',
        UNIQUE (document_id, page, content_hash)
    );

    CREATE INDEX IF NOT EXISTS idx_document_chunks_document
        ON document_chunks(document_id);
    CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
        ON document_chunks USING hnsw (embedding vector_cosine_ops);
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=5)
            await self._execute_schema()

    async def _execute_schema(self) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(self.SCHEMA_SQL)

    async def upsert_document(self, document: Document) -> None:
        await self.initialize()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (
                    id, title, file_path, file_type, page_count, project_folder_id,
                    visible_department_ids, visible_role_ids, status, uploaded_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    file_path = EXCLUDED.file_path,
                    file_type = EXCLUDED.file_type,
                    page_count = EXCLUDED.page_count,
                    project_folder_id = EXCLUDED.project_folder_id,
                    visible_department_ids = EXCLUDED.visible_department_ids,
                    visible_role_ids = EXCLUDED.visible_role_ids,
                    status = EXCLUDED.status
                """,
                document.id,
                document.title,
                document.file_path,
                document.file_type,
                document.page_count,
                document.project_folder_id,
                document.visible_department_ids,
                document.visible_role_ids,
                document.status,
                document.uploaded_by,
            )

    async def insert_chunks(self, chunks: list[DocumentChunk]) -> None:
        await self.initialize()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            for chunk in chunks:
                if not chunk.content_hash:
                    chunk.content_hash = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
                embedding_arg = _vector_literal(chunk.embedding) if chunk.embedding else None
                await conn.execute(
                    """
                    INSERT INTO document_chunks (
                        id, document_id, page, chapter, start_offset, end_offset,
                        content, content_hash, embedding, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector, $10::jsonb)
                    ON CONFLICT (document_id, page, content_hash) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                    """,
                    chunk.id or str(uuid.uuid4()),
                    chunk.document_id,
                    chunk.page,
                    chunk.chapter,
                    chunk.start_offset,
                    chunk.end_offset,
                    chunk.content,
                    chunk.content_hash,
                    embedding_arg,
                    json.dumps(chunk.metadata, ensure_ascii=False),
                )

    async def fetch_allowed_chunks(
        self,
        user: UserContext,
        limit: int | None = None,
    ) -> list[RetrievedChunk]:
        """在权限过滤后取回全部候选切片（不含向量），供 BM25 打分。"""
        await self.initialize()
        assert self._pool is not None
        query = """
            SELECT c.id AS chunk_id, c.document_id, d.title AS document_name,
                   c.page, c.content, c.metadata
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.project_folder_id = ANY($1::text[])
               OR d.visible_department_ids && $2::text[]
            ORDER BY c.document_id, c.page
        """
        args: list[Any] = [user.project_ids, user.department_ids]
        if limit is not None:
            query += " LIMIT $3"
            args.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
        return [self._row_to_retrieved(row, score=0.0) for row in rows]

    async def fetch_allowed_semantic_candidates(
        self,
        user: UserContext,
        query_embedding: list[float],
        limit: int,
    ) -> list[RetrievedChunk]:
        """权限过滤后使用 pgvector 余弦相似度取候选。"""
        await self.initialize()
        assert self._pool is not None
        query = """
            SELECT c.id AS chunk_id, c.document_id, d.title AS document_name,
                   c.page, c.content, c.metadata,
                   1 - (c.embedding <=> $3::vector) AS similarity
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND (d.project_folder_id = ANY($1::text[])
                   OR d.visible_department_ids && $2::text[])
            ORDER BY c.embedding <=> $3::vector
            LIMIT $4
        """
        embedding_arg = _vector_literal(query_embedding)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                user.project_ids,
                user.department_ids,
                embedding_arg,
                limit,
            )
        return [
            self._row_to_retrieved(row, score=float(row["similarity"] or 0.0))
            for row in rows
        ]

    async def delete_document(self, document_id: str) -> None:
        await self.initialize()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM documents WHERE id = $1", document_id)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @staticmethod
    def _row_to_retrieved(row: asyncpg.Record, score: float) -> RetrievedChunk:
        metadata = dict(row.get("metadata") or {})
        return RetrievedChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            document_name=row["document_name"],
            page=row["page"],
            content=row["content"],
            score=score,
            metadata=metadata,
        )
