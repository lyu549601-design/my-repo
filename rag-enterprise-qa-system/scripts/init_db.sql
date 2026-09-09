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
