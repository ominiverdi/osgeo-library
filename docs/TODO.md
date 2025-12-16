# OSGeo Library - Knowledge Base TODO

## Overview

Build a PostgreSQL + pgvector knowledge base from extracted PDF content, with an agentic bot interface for semantic search and multi-modal responses (text + images).

---

## Phase 1: Database Schema

### Tables

```sql
-- Documents (papers)
documents: id, slug, title, source_file, extraction_date, model, metadata

-- Pages
pages: id, document_id, page_number, image_path, annotated_image_path, 
       full_text, width, height

-- Text chunks (for RAG)
chunks: id, document_id, page_id, content, chunk_index, start_char, end_char,
        embedding vector(1024), metadata

-- Elements (figures, tables, equations)
elements: id, document_id, page_id, element_type, label, description,
          search_text, latex, crop_path, rendered_path, bbox_pixels,
          embedding vector(1024), metadata
```

### Indexes
- ivfflat on chunks.embedding
- ivfflat on elements.embedding

---

## Phase 2: Equation Enrichment

Before ingestion, run a second LLM pass on equations to generate searchable descriptions.

**Input:**
- Equation label
- LaTeX content
- Full page text (for context)

**Prompt:**
```
Given this equation from a scientific paper:
Label: {label}
LaTeX: {latex}

And the page content where it appears:
{page_text}

Describe what this equation represents, what it calculates, and how it's used.
Focus on making it searchable - include key terms a researcher might use.
```

**Output:** Rich description stored in `elements.search_text`

**Estimate:** ~60 seconds per equation with Qwen3-VL-235B

---

## Phase 3: Ingestion Pipeline

Script: `ingest_to_db.py`

```
extraction.json -> Parse -> Chunk text -> Enrich equations -> Embed -> Insert
```

### Steps:
1. Read extraction.json
2. Create document record
3. For each page:
   - Create page record
   - Chunk text (~800 tokens, 200 overlap)
   - Embed each chunk
   - Insert chunks
4. For each element:
   - If equation: generate enriched search_text (LLM call)
   - Else: use existing description as search_text
   - Embed search_text
   - Insert element

### Embedding Model
- Local: nomic-embed-text or mxbai-embed-large via llama.cpp
- Dimensions: 768-1024

---

## Phase 4: Search Service

Script: `search_service.py`

### Function: `search_knowledge(query, doc_filter, element_types, limits)`

1. Embed query
2. Parallel search:
   - chunks: top 5 by cosine similarity
   - elements: top 3 by cosine similarity
3. Get linked elements (same pages as matching chunks)
4. Merge & deduplicate
5. Return structured result

### Response Format:
```python
{
  "query": str,
  "chunks": [
    {"content": str, "document": str, "page": int, "similarity": float}
  ],
  "elements": [
    {"id": int, "type": str, "label": str, "description": str,
     "image_path": str, "document": str, "page": int,
     "match_type": "direct"|"linked", "similarity": float|null}
  ]
}
```

---

## Phase 5: Bot Tools

### Tools for Agentic Bot:

1. **search_knowledge(query, doc_filter?, element_types?, limit?)**
   - Semantic search across all content
   - Returns chunks + elements

2. **get_sources()**
   - Returns citation info for last search
   - Document, page, similarity for each source

3. **get_element(element_id?, document?, label?)**
   - Fetch specific figure/table/equation
   - Returns metadata + image path

4. **show_page(document, page_number, annotated?)**
   - Returns page image path
   - Option for annotated version with bounding boxes

5. **list_elements(document?, element_type?)**
   - List available elements
   - Filter by document or type

---

## Phase 6: Matrix Bot Integration

Script: `bot/matrix_bot.py`

### Features:
- Listen for messages in configured rooms
- Maintain conversation context (last search results)
- Answer questions using search_knowledge
- Offer to show images
- Upload images when user confirms
- Cite sources on request

### Image Delivery:
- Matrix: upload image directly to room
- CLI (testing): return local file path

### Configuration:
- Local Matrix instance for testing
- Remote Matrix instance for production
- PostgreSQL: local for testing, remote for production

---

## File Structure

```
/home/ominiverdi/github/osgeo-library/
├── extract_document.py      # Single-document extraction (web viewer format)
├── extract_all_pages.py     # Batch extraction (db/data format, resumable)
├── migrate_to_db.py         # Convert web/data -> db/data structure
├── run_extraction.sh        # Overnight batch runner
├── ingest_to_db.py          # TODO: Load extractions into PostgreSQL
├── search_service.py        # TODO: Query interface
├── bot/
│   ├── __init__.py
│   ├── matrix_bot.py        # TODO: Matrix client
│   ├── tools.py             # TODO: Tool definitions
│   ├── agent.py             # TODO: Agentic loop
│   └── context.py           # TODO: Conversation context
├── db/
│   ├── schema.sql           # TODO: PostgreSQL schema
│   ├── connection.py        # TODO: DB connection
│   ├── migrations/          # TODO: Schema migrations
│   └── data/                # Extracted content (per-page JSON, images, elements)
│       ├── sam3/
│       │   ├── document.json
│       │   ├── pages/page_001.json, ...
│       │   ├── images/page_001.png, ...
│       │   └── elements/p01_figure_1_*.png, ...
│       ├── usgs_snyder/
│       └── alpine_change/
├── embeddings/
│   └── embed.py             # TODO: Embedding generation
└── web/
    └── data/                # Demo extractions (monolithic JSON, subset of pages)
```

---

## Retrieval Flow

```
USER QUERY
    |
    v
EMBED QUERY (local model)
    |
    +---> SEARCH CHUNKS (top 5 by cosine similarity)
    |
    +---> SEARCH ELEMENTS (top 3 by cosine similarity)
    |
    v
GET LINKED ELEMENTS (same pages as matching chunks)
    |
    v
MERGE & DEDUPLICATE
    |
    v
RETURN TO BOT:
{
  chunks: [...],
  elements: [
    {type, label, description, image_path, match_type: "direct"|"linked"}
  ]
}
    |
    v
BOT SYNTHESIZES RESPONSE
- Answers question from chunk content
- Mentions relevant figures/tables/equations
- Offers to show images
- Can cite sources on follow-up question
```

---

## Citation Flow

When user asks "where did you find that?":

1. Bot stores last SearchResult in conversation context
2. On citation request, formats stored results:
   - Document slug, page number, similarity for each chunk
   - Related elements with labels and descriptions
3. Can offer to show original page or specific elements

---

## Open Questions

1. **Similarity threshold**: Filter results below 0.5, or always return top N?

2. **Linked element cap**: Return all elements on matching pages, or cap at 5?

3. **Cross-document weighting**: Boost results from mentioned document?

4. **Reranker**: Use simple similarity, or add BGE-reranker for precision?

5. **Chunk size**: 800 tokens with 200 overlap - confirm this is good for scientific papers?

---

## Next Session: Implementation Order

1. [ ] Create `db/schema.sql`
2. [ ] Create `embeddings/embed.py` (local model setup)
3. [ ] Create equation enrichment script (LLM second pass)
4. [ ] Create `ingest_to_db.py`
5. [ ] Test ingestion with sam3 extraction
6. [ ] Create `search_service.py`
7. [ ] Test search queries
8. [ ] Create bot tools
9. [ ] Create Matrix bot skeleton
10. [ ] Integration testing
