# Architecture

High-level overview of the OSGeo Library system.

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENTS                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Rust CLI    │  │  Matrix Bot  │  │  Web UI      │           │
│  │  (osgeo-lib) │  │  (planned)   │  │  (planned)   │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          │                 │                 │
          └────────────────┬┴─────────────────┘
                           │ HTTP :8095
                           v
┌─────────────────────────────────────────────────────────────────┐
│                    API SERVER (FastAPI)                          │
│  server.py                                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  /search    /chat    /documents/search    /page/{n}     │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────┬───────────────────┬──────────────────────────────┘
               │                   │
       ┌───────┴───────┐   ┌───────┴───────┐
       v               v   v               v
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  BGE-M3      │ │  PostgreSQL  │ │  LLM         │
│  Embeddings  │ │  + pgvector  │ │  (OpenRouter │
│  :8094       │ │              │ │   or local)  │
└──────────────┘ └──────────────┘ └──────────────┘
```

## Components

| Component | Description |
|-----------|-------------|
| **API Server** | FastAPI serving REST endpoints for search, chat, page browsing |
| **Embedding Server** | llama.cpp serving BGE-M3 for query/document embeddings |
| **Database** | PostgreSQL with pgvector for semantic similarity search |
| **LLM** | Qwen3-30B (local) or OpenRouter for chat responses |

## Data Flow

### Extraction (offline)

```
PDF → Qwen3-VL-235B → Elements + Text → Qwen3-30B (enrichment) → BGE-M3 → PostgreSQL
```

See [EXTRACTION.md](EXTRACTION.md) for details.

### Search (online)

```
Query → BGE-M3 embed → pgvector similarity → Ranked results
                    → BM25 keyword match  ↗
```

### Chat (online)

```
Question → Search → Top results as context → LLM → Answer with citations
```

## Database Schema

```
documents: id, slug, title, source_file, extraction_date, model, metadata
pages: id, document_id, page_number, image_path, full_text, width, height
chunks: id, document_id, page_id, content, chunk_index, embedding vector(1024)
elements: id, document_id, page_id, element_type, label, description,
          search_text, latex, crop_path, embedding vector(1024)
```

## Search

Hybrid search combining semantic and keyword matching:

1. **Semantic** - BGE-M3 embeddings with cosine similarity (pgvector)
2. **BM25** - PostgreSQL full-text search (tsvector/GIN index)

Results are merged and deduplicated, keeping the best score for each document.

### Scoring

| Distance | Score | Interpretation |
|----------|-------|----------------|
| 0.30-0.60 | 100% | Exact/near-exact match |
| 0.70-0.85 | 50-100% | Highly relevant |
| 0.85-0.94 | 20-50% | Moderately relevant |
| >0.94 | <20% | Filtered out |

## Related Documentation

- [API.md](API.md) - REST endpoint reference
- [CLIENT.md](CLIENT.md) - Rust CLI user guide
- [DECISIONS.md](DECISIONS.md) - Technical choices and rationale
- [DEPLOYMENT.md](DEPLOYMENT.md) - Server setup and maintenance
- [EXTRACTION.md](EXTRACTION.md) - PDF processing pipeline
