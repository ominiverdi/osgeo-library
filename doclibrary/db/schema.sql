-- OSGeo Library Database Schema
-- PostgreSQL + pgvector

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents (papers)
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(255) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    source_file VARCHAR(255) UNIQUE NOT NULL,
    extraction_date TIMESTAMP NOT NULL,
    model VARCHAR(100) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    summary TEXT,
    keywords TEXT[],
    license TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pages
CREATE TABLE pages (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    image_path VARCHAR(500) NOT NULL,
    annotated_image_path VARCHAR(500),
    full_text TEXT,
    summary TEXT,
    keywords TEXT[],
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, page_number)
);

-- Text chunks (for RAG)
CREATE TABLE chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    start_char INTEGER,
    end_char INTEGER,
    embedding vector(1024),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Elements (figures, tables, equations, diagrams, charts)
CREATE TABLE elements (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    element_type VARCHAR(50) NOT NULL,
    label VARCHAR(100),
    description TEXT,
    search_text TEXT,
    latex TEXT,
    crop_path VARCHAR(500),
    rendered_path VARCHAR(500),
    bbox_pixels INTEGER[4],
    embedding vector(1024),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for foreign keys
CREATE INDEX idx_pages_document_id ON pages(document_id);
CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_chunks_page_id ON chunks(page_id);
CREATE INDEX idx_elements_document_id ON elements(document_id);
CREATE INDEX idx_elements_page_id ON elements(page_id);

-- Indexes for common queries
CREATE INDEX idx_elements_type ON elements(element_type);
CREATE INDEX idx_documents_slug ON documents(slug);
CREATE INDEX idx_documents_source_file ON documents(source_file);

-- Full-text search (tsvector) columns and indexes
-- These enable BM25-style keyword matching alongside semantic search

-- Add tsvector columns for full-text search
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

ALTER TABLE elements ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', 
        coalesce(label, '') || ' ' || 
        coalesce(description, '') || ' ' || 
        coalesce(search_text, '')
    )) STORED;

-- GIN indexes for fast full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN(tsv);
CREATE INDEX IF NOT EXISTS idx_elements_tsv ON elements USING GIN(tsv);

-- Full-text search on summaries
ALTER TABLE pages ADD COLUMN IF NOT EXISTS summary_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(summary, ''))) STORED;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS summary_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(summary, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_pages_summary_tsv ON pages USING GIN(summary_tsv);
CREATE INDEX IF NOT EXISTS idx_documents_summary_tsv ON documents USING GIN(summary_tsv);

-- GIN indexes for keyword array search (for @> containment queries)
CREATE INDEX IF NOT EXISTS idx_pages_keywords ON pages USING GIN(keywords);
CREATE INDEX IF NOT EXISTS idx_documents_keywords ON documents USING GIN(keywords);

-- Vector indexes (ivfflat) for similarity search
-- Note: Create these AFTER loading data for better index quality
-- Lists parameter should be ~ sqrt(row_count), minimum 100

-- For chunks: assuming ~10k chunks initially
CREATE INDEX idx_chunks_embedding ON chunks 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- For elements: assuming ~1k elements initially
CREATE INDEX idx_elements_embedding ON elements 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Helper function: cosine similarity search on chunks
CREATE OR REPLACE FUNCTION search_chunks(
    query_embedding vector(1024),
    match_count INTEGER DEFAULT 5,
    doc_filter INTEGER DEFAULT NULL
)
RETURNS TABLE (
    chunk_id INTEGER,
    document_id INTEGER,
    page_id INTEGER,
    content TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.document_id,
        c.page_id,
        c.content,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    WHERE (doc_filter IS NULL OR c.document_id = doc_filter)
      AND c.embedding IS NOT NULL
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Helper function: cosine similarity search on elements
CREATE OR REPLACE FUNCTION search_elements(
    query_embedding vector(1024),
    match_count INTEGER DEFAULT 3,
    doc_filter INTEGER DEFAULT NULL,
    type_filter VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    element_id INTEGER,
    document_id INTEGER,
    page_id INTEGER,
    element_type VARCHAR,
    label VARCHAR,
    description TEXT,
    search_text TEXT,
    crop_path VARCHAR,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id,
        e.document_id,
        e.page_id,
        e.element_type,
        e.label,
        e.description,
        e.search_text,
        e.crop_path,
        1 - (e.embedding <=> query_embedding) AS similarity
    FROM elements e
    WHERE (doc_filter IS NULL OR e.document_id = doc_filter)
      AND (type_filter IS NULL OR e.element_type = type_filter)
      AND e.embedding IS NOT NULL
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;
