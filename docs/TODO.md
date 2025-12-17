# OSGeo Library - Knowledge Base TODO

## Overview

Build a PostgreSQL + pgvector knowledge base from extracted PDF content, with an agentic bot interface for semantic search and multi-modal responses (text + images).

---

## Phase 1: Database Schema

### Tables

```sql
-- Documents (papers)
documents: id, slug, title, source_file, extraction_date, model, metadata
-- title: cleaned from slug (remove underscores, .pdf, etc.)

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
-- description: original extraction output (visual description or LaTeX)
-- search_text: enriched contextual description for retrieval (from Phase 2)
-- latex: parsed from description for equations, NULL for other types
-- embedding: vector of search_text, not description
```

### Indexes
- ivfflat on chunks.embedding
- ivfflat on elements.embedding

---

## Phase 2: Element Enrichment (Second LLM Pass)

Before ingestion, run a second LLM pass on **all elements** to generate contextual, searchable descriptions. This enhances retrieval by connecting elements to their surrounding content.

### Why Enrich All Elements?

| Element Type | `description` (from extraction) | `search_text` (enriched) |
|--------------|--------------------------------|--------------------------|
| **Equation** | Raw LaTeX notation | Semantic explanation: what it calculates, key terms, how it relates to the paper |
| **Figure** | Visual description of what's shown | Contextual role: why this figure matters, what concepts it illustrates, research relevance |
| **Table** | Column headers and data summary | Analytical context: what comparisons it enables, key findings, benchmark significance |
| **Diagram** | Components and flow description | Methodological context: where it fits in the pipeline, what process it documents |

### Enrichment Prompt

```
Given this {element_type} from a scientific paper:
Label: {label}
Original description: {description}

Page context:
{page_text}

Describe how this element relates to the document's content.
What concepts does it illustrate? What would a researcher search
for when looking for this? Include key terms and relationships.
```

### Example Enrichments

**Equation** (usgs_snyder):
- `description`: `LaTeX: \sin \phi = \sin \alpha \sin \phi' + \cos \alpha \cos \phi' \cos (\lambda' - \beta)`
- `search_text`: "Spherical trigonometry equation for calculating projected latitude in the Oblique Mercator projection. Transforms coordinates from oblique to standard coordinate system. Key terms: latitude, longitude, azimuth, map projection, coordinate transformation."

**Figure** (alpine_change):
- `description`: "Map of the study area showing Gesäuse National Park in Styria, Austria..."
- `search_text`: "Study area map establishing geographic context for habitat classification research. Shows temporal coverage of HabitAlp datasets (2013, 2020) in Austrian Alps. Relevant for: ecological monitoring, national park boundaries, alpine habitat mapping, Austria remote sensing."

**Table** (sam3):
- `description`: "Evaluation metrics for image segmentation models across LVIS, COCO, SA-Co..."
- `search_text`: "Benchmark comparison showing SAM 3 achieving state-of-the-art performance on open-vocabulary segmentation. Compares against OWLv2, DINO-X, Gemini 2.5. Key metrics: CGF1, AP, IoU. Useful for: model selection, segmentation baselines, computer vision benchmarks."

### Processing

- Script: `enrich_elements.py`
- Input: Extracted JSON files from `db/data/{document}/`
- Output: Updated JSON with `search_text` field populated
- Estimate: ~60 seconds per element with Qwen3-VL-235B (or faster with lighter model for text-only enrichment)

---

## Phase 3: Ingestion Pipeline

Script: `ingest_to_db.py`

```
db/data/{document}/ -> Parse -> Chunk text -> Embed -> Insert
```

### Steps:
1. Read document.json and page JSON files
2. Create document record (title = cleaned slug)
3. For each page:
   - Create page record
   - Chunk text (~800 tokens, 200 overlap)
   - Embed each chunk
   - Insert chunks
4. For each element:
   - Parse `latex` from description (if equation)
   - Use `search_text` for embedding (populated by Phase 2)
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

## Implementation Progress

1. [x] Create `db/schema.sql` - PostgreSQL + pgvector schema
2. [x] Create `embeddings/embed.py` - BGE-M3 via llama.cpp (port 8094)
3. [x] Create `enrich_elements.py` - Qwen3-30B enrichment
4. [x] Create `db/connection.py` - database helpers
5. [x] Create `db/chunking.py` - text chunking with sentence breaks
6. [x] Create `ingest_to_db.py` - full ingestion pipeline
7. [x] Run enrichment on all documents (1131 elements enriched)
8. [x] Run ingestion to database (3 docs, 488 pages, 2195 chunks, 1131 elements)
9. [x] Create `search_service.py` - semantic search with pgvector
10. [x] Test search queries (working)
11. [ ] Create bot tools
12. [ ] Create Matrix bot skeleton
13. [ ] Integration testing
