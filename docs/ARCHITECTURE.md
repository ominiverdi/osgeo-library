# Architecture

High-level overview of the doclibrary system.

## System Overview

```
                              CLIENTS
  +-------------+  +-------------+  +-------------+  +-------------+
  | doclibrary  |  | Claude      |  | REST        |  | Web UI      |
  | CLI (chat)  |  | Desktop     |  | Clients     |  | (planned)   |
  +------+------+  +------+------+  +------+------+  +------+------+
         |                |                |                |
         |                | MCP            | HTTP           |
         v                v                v                v
  +------+------+  +------+------+  +------+----------------+------+
  | Chat Module |  | MCP Server  |  |      REST API Server        |
  | (direct)    |  | (FastMCP)   |  |      (FastAPI :8000)        |
  +------+------+  +------+------+  +------+----------------+------+
         |                |                |
         +----------------+----------------+
                          |
         +----------------+----------------+----------------+
         |                |                |                |
         v                v                v                v
  +------+------+  +------+------+  +------+------+  +------+------+
  | Search      |  | PostgreSQL  |  | BGE-M3      |  | LLM         |
  | Service     |  | + pgvector  |  | Embeddings  |  | (local or   |
  |             |  |             |  | :8094       |  |  OpenRouter)|
  +-------------+  +-------------+  +-------------+  +-------------+
```

## Package Structure

```
doclibrary/
  __init__.py
  cli.py                 # Main CLI entry point (argparse)
  config.py              # Configuration from TOML/env vars

  core/                  # Shared utilities
    __init__.py
    constants.py         # System prompt, element types, stopwords
    formatting.py        # Context/source formatting for LLM
    image.py             # Image annotation (bounding boxes)
    llm.py               # LLM client (OpenAI-compatible)
    text.py              # Text processing utilities

  db/                    # Database layer
    __init__.py
    connection.py        # PostgreSQL connection, CRUD operations
    chunking.py          # Text chunking for RAG
    ingest.py            # Document ingestion pipeline
    schema.sql           # Database schema
    migrations/          # Schema migrations

  search/                # Search functionality
    __init__.py
    embeddings.py        # BGE-M3 embedding generation
    service.py           # Hybrid search (semantic + BM25)

  extraction/            # PDF processing
    __init__.py
    document.py          # PDF extraction with vision LLM
    enrichment.py        # Generate search_text for elements

  chat/                  # Interactive chat
    __init__.py
    context.py           # Multi-turn conversation context
    display.py           # Terminal preview (chafa), GUI viewer
    query.py             # Query processing, follow-up expansion
    commands.py          # Chat commands (show, open, sources)

  servers/               # Server implementations
    __init__.py
    api.py               # FastAPI REST server
    mcp.py               # MCP server for Claude Desktop
```

## Components

| Component | Description |
|-----------|-------------|
| **CLI** | Unified `doclibrary` command with subcommands |
| **REST API** | FastAPI server for HTTP clients |
| **MCP Server** | Model Context Protocol for Claude Desktop |
| **Search Service** | Hybrid semantic + keyword search |
| **Embedding Server** | llama.cpp serving BGE-M3 |
| **Database** | PostgreSQL with pgvector |
| **LLM** | Qwen3-30B (local) or OpenRouter |

### PDF Processing Stack

| Component | Role |
|-----------|------|
| **PyMuPDF (fitz)** | PDF rendering, text extraction |
| **Vision LLM** | Element detection with bounding boxes |
| **PIL/Pillow** | Element cropping |
| **pdflatex + ImageMagick** | LaTeX rendering |

## Data Flow

### Extraction Pipeline

```
PDF --> PyMuPDF --> Page images (PNG) --> Vision LLM --> Element bboxes
                                                              |
                                                              v
                                                    PIL crops elements
                                                              |
                                                              v
                                        Enrichment LLM --> search_text
                                                              |
                                                              v
                                                    BGE-M3 --> embeddings
                                                              |
                                                              v
                                                         PostgreSQL
```

CLI commands:
```bash
doclibrary extract paper.pdf --output-dir db/data/paper
doclibrary enrich paper       # Generates search_text + summaries + keywords
doclibrary ingest paper       # Loads into PostgreSQL with embeddings
```

### Search Flow

```
Query --> BGE-M3 embed --> pgvector similarity --+
      |                                          |--> Merge & rank --> Results
      +--> Keyword extraction --> BM25 search ---+
```

### Chat Flow

```
Question --> Search --> Top results as context --> LLM --> Answer with citations
```

## Database Schema

```sql
documents: id, slug, title, source_file, extraction_date, model, metadata,
           summary, keywords[], license
pages: id, document_id, page_number, image_path, full_text, width, height,
       summary, keywords[]
chunks: id, document_id, page_id, content, chunk_index, embedding, tsv
elements: id, document_id, page_id, element_type, label, description,
          search_text, latex, crop_path, rendered_path, embedding, tsv
```

### Summary Fields (v2.1.0)

- **Document summary**: 3-5 sentences, generated from page summaries
- **Document keywords**: 10 keywords capturing main topics
- **Document license**: Extracted from first/last pages (if found)
- **Page summary**: 2-3 sentences per page
- **Page keywords**: 8 keywords per page

## Configuration

Settings loaded from (in priority order):

1. **Environment variables** - `DOCLIBRARY_*` prefix
2. **config.local.toml** - Local overrides (gitignored)
3. **config.toml** - Project configuration
4. **~/.config/doclibrary/config.toml** - User configuration

### Environment Variables

```bash
DOCLIBRARY_LLM_URL          # LLM API endpoint
DOCLIBRARY_LLM_MODEL        # Model name for chat
DOCLIBRARY_LLM_API_KEY      # API key (for OpenRouter)
DOCLIBRARY_VISION_LLM_URL   # Vision LLM endpoint
DOCLIBRARY_VISION_LLM_MODEL # Vision model name
DOCLIBRARY_EMBED_URL        # Embedding server endpoint
DOCLIBRARY_EMBED_DIM        # Embedding dimensions (default: 1024)
DOCLIBRARY_DATA_DIR         # Path to extracted data
DOCLIBRARY_DB_NAME          # PostgreSQL database name
DOCLIBRARY_DB_HOST          # Database host (empty for Unix socket)
DOCLIBRARY_DB_PORT          # Database port
DOCLIBRARY_DB_USER          # Database user
```

### Config File Format

```toml
[llm]
url = "http://localhost:8080/v1/chat/completions"
model = "qwen3-30b"
temperature = 0.3

[vision_llm]
url = "http://localhost:8090/v1"
model = "qwen2-vl-7b"

[embedding]
url = "http://localhost:8094/embedding"
dimensions = 1024

[database]
name = "osgeo_library"
# host, port, user, password optional for peer auth

[paths]
data_dir = "data"

[display]
chafa_size = "80x35"
```

## Search

Hybrid search combining semantic and keyword matching:

1. **Semantic** - BGE-M3 embeddings with L2 distance (pgvector)
2. **BM25** - PostgreSQL full-text search (tsvector/GIN index)
3. **Keyword extraction** - Natural language to keywords for better BM25

Results are merged and deduplicated, keeping the best score for each result.

### Scoring

| Distance | Score | Interpretation |
|----------|-------|----------------|
| 0.30-0.60 | 100% | Exact/near-exact match |
| 0.70-0.85 | 50-100% | Highly relevant |
| 0.85-0.94 | 20-50% | Moderately relevant |
| >0.94 | <20% | Filtered out |

## Testing

```bash
# Unit tests (no external dependencies)
pytest tests/unit/ -v

# Integration tests (requires postgres, embedding server)
pytest tests/ --run-integration

# Coverage report
pytest tests/unit/ --cov=doclibrary --cov-report=html
```

## Related Documentation

- [API.md](API.md) - REST and MCP endpoint reference
- [CLIENT.md](CLIENT.md) - Rust CLI user guide  
- [DECISIONS.md](DECISIONS.md) - Technical choices and rationale
- [DEPLOYMENT.md](DEPLOYMENT.md) - Server setup and maintenance
- [EXTRACTION.md](EXTRACTION.md) - PDF processing pipeline details
