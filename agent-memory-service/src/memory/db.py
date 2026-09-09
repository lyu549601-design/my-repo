"""记忆系统的 PostgreSQL + pgvector 存取层。"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import asyncpg
import structlog

from .models import MemoryChunk

logger = structlog.get_logger()


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


class MemoryPostgres:
    """基于 asyncpg 的 pgvector 存储。"""

    SCHEMA_SQL = """
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE TABLE IF NOT EXISTS memory_chunks (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        source_task TEXT NOT NULL,
        chunk_type TEXT NOT NULL,
        content TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        embedding vector(512),
        importance REAL NOT NULL DEFAULT 0.5,
        access_count INTEGER NOT NULL DEFAULT 0,
        last_access_at TIMESTAMP WITH TIME ZONE,
        metadata JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (task_id, source_task, chunk_type, content_hash)
    );
    CREATE INDEX IF NOT EXISTS idx_memory_chunks_task
        ON memory_chunks(task_id);
    CREATE INDEX IF NOT EXISTS idx_memory_chunks_embedding
        ON memory_chunks USING hnsw (embedding vector_cosine_ops);
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=5)
            await self._execute_schema()
            logger.info("memory_postgres.initialized")

    async def _execute_schema(self) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(self.SCHEMA_SQL)

    async def upsert_chunk(self, chunk: MemoryChunk) -> MemoryChunk:
        await self.initialize()
        assert self._pool is not None

        if not chunk.id:
            chunk.id = str(uuid.uuid4())
        if not chunk.content_hash:
            chunk.content_hash = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()

        embedding_arg: str | None = (
            _vector_literal(chunk.embedding) if chunk.embedding else None
        )
        metadata_json = json.dumps(chunk.metadata, ensure_ascii=False)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_chunks (
                    id, task_id, source_task, chunk_type, content, content_hash,
                    embedding, importance, access_count, last_access_at, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8, $9, $10, $11::jsonb)
                ON CONFLICT (task_id, source_task, chunk_type, content_hash)
                DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    importance = EXCLUDED.importance,
                    metadata = EXCLUDED.metadata
                """,
                chunk.id,
                chunk.task_id,
                chunk.source_task,
                chunk.chunk_type,
                chunk.content,
                chunk.content_hash,
                embedding_arg,
                chunk.importance,
                chunk.access_count,
                chunk.last_access_at,
                metadata_json,
            )
        return chunk

    async def fetch_chunks(
        self,
        task_id: str,
        chunk_type: str | None = None,
        source_task: str | None = None,
    ) -> list[MemoryChunk]:
        await self.initialize()
        assert self._pool is not None

        query = """
            SELECT id, task_id, source_task, chunk_type, content, content_hash,
                   importance, access_count, last_access_at, metadata, created_at
            FROM memory_chunks
            WHERE task_id = $1
        """
        args: list[Any] = [task_id]
        if chunk_type:
            query += " AND chunk_type = $2"
            args.append(chunk_type)
        if source_task:
            query += f" AND source_task = ${len(args) + 1}"
            args.append(source_task)
        query += " ORDER BY created_at DESC"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
        return [self._row_to_chunk(row) for row in rows]

    async def fetch_semantic_candidates(
        self,
        task_id: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[MemoryChunk]:
        await self.initialize()
        assert self._pool is not None

        query = """
            SELECT id, task_id, source_task, chunk_type, content, content_hash,
                   importance, access_count, last_access_at, metadata, created_at,
                   1 - (embedding <=> $2::vector) AS similarity
            FROM memory_chunks
            WHERE task_id = $1 AND chunk_type = 'evidence_summary'
              AND embedding IS NOT NULL
            ORDER BY embedding <=> $2::vector
            LIMIT $3
        """
        embedding_arg = _vector_literal(query_embedding)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, task_id, embedding_arg, limit)
        return [self._row_to_chunk(row) for row in rows]

    async def fetch_feedback(
        self,
        task_id: str,
        source_task: str,
        retry_count: int,
    ) -> MemoryChunk | None:
        await self.initialize()
        assert self._pool is not None

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, task_id, source_task, chunk_type, content, content_hash,
                       importance, access_count, last_access_at, metadata, created_at
                FROM memory_chunks
                WHERE task_id = $1
                  AND source_task = $2
                  AND chunk_type = 'review_feedback'
                  AND metadata->>'retry_count' = $3::text
                ORDER BY created_at DESC
                LIMIT 1
                """,
                task_id,
                source_task,
                str(retry_count),
            )
        return self._row_to_chunk(row) if row else None

    async def increment_access(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        await self.initialize()
        assert self._pool is not None

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_chunks
                SET access_count = access_count + 1,
                    last_access_at = CURRENT_TIMESTAMP
                WHERE id = ANY($1::text[])
                """,
                chunk_ids,
            )

    async def delete_task(self, task_id: str) -> None:
        if self._pool is None:
            return
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM memory_chunks WHERE task_id = $1", task_id)
        logger.info("memory_postgres.task_cleared", task_id=task_id)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @staticmethod
    def _row_to_chunk(row: asyncpg.Record) -> MemoryChunk:
        metadata = dict(row.get("metadata") or {})
        return MemoryChunk(
            id=row["id"],
            task_id=row["task_id"],
            source_task=row["source_task"],
            chunk_type=row["chunk_type"],
            content=row["content"],
            content_hash=row["content_hash"],
            embedding=None,
            semantic_similarity=row.get("similarity"),
            importance=row["importance"],
            access_count=row["access_count"],
            last_access_at=row["last_access_at"],
            metadata=metadata,
            created_at=row["created_at"],
        )
