-- Applied on every startup by app/db.py:apply_schema. Every statement must be idempotent.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),  -- UUID v4
    title         text        NOT NULL CHECK (title <> ''),
    source_path   text        NOT NULL,
    content_hash  char(64)    NOT NULL UNIQUE,  -- SHA-256 hex of the PDF bytes (idempotent ingest)
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     uuid        NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    strategy        text        NOT NULL CHECK (strategy IN ('naive', 'section_aware')),
    chunk_index     int         NOT NULL,
    clause_id       text,                       -- NULL for naive chunks
    parent_heading  text,
    page            int         NOT NULL,
    content         text        NOT NULL,
    embedding       vector(768) NOT NULL,       -- dimension fixed by the embedding model
    -- Also serves as the index for "chunks WHERE document_id = ?" (leftmost column).
    UNIQUE (document_id, strategy, chunk_index)
);

-- Approximate nearest-neighbour index for cosine distance (the `<=>` operator).
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
