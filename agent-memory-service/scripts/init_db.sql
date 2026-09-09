-- Agent 记忆服务数据库初始化
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
