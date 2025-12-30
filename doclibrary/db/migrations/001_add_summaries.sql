-- Migration 001: Add summary, keywords, and license columns
-- Run with: psql osgeo_library < doclibrary/db/migrations/001_add_summaries.sql

-- Documents: add summary, keywords, license
ALTER TABLE documents ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS keywords TEXT[];
ALTER TABLE documents ADD COLUMN IF NOT EXISTS license TEXT;

-- Pages: add summary, keywords
ALTER TABLE pages ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS keywords TEXT[];

-- Add full-text search on summaries
ALTER TABLE pages ADD COLUMN IF NOT EXISTS summary_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(summary, ''))) STORED;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS summary_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(summary, ''))) STORED;

-- GIN indexes for summary search
CREATE INDEX IF NOT EXISTS idx_pages_summary_tsv ON pages USING GIN(summary_tsv);
CREATE INDEX IF NOT EXISTS idx_documents_summary_tsv ON documents USING GIN(summary_tsv);

-- GIN indexes for keyword array search (for @> containment queries)
CREATE INDEX IF NOT EXISTS idx_pages_keywords ON pages USING GIN(keywords);
CREATE INDEX IF NOT EXISTS idx_documents_keywords ON documents USING GIN(keywords);
