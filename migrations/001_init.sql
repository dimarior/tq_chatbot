CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id              BIGSERIAL PRIMARY KEY,
    url             TEXT UNIQUE NOT NULL,
    source          TEXT NOT NULL,
    title           TEXT,
    content_hash    TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL,
    last_indexed_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS documents_source_idx ON documents(source);

CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL,
    content      TEXT NOT NULL,
    embedding    vector(1024) NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks(document_id);
