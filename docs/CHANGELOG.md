# Changelog

Brief log of what changed and when.

## 2025-12-29 (v2.2.0)

### New Features
- **REST API Document Endpoints**: Full document browsing capabilities
  - `GET /documents` - Paginated list with summaries, keywords, license
  - `GET /documents/{slug}` - Document details with element counts
  - Page endpoint now includes summary and keywords
- **Rust CLI Document Commands**:
  - `osgeo-library docs` - List all documents with summaries
  - `osgeo-library doc <slug>` - Show document details, keywords, element counts
- **MCP Server Enhancements**: Tools now return summaries and keywords
  - `list_documents` - Includes summaries (truncated for list view)
  - `list_documents_paginated` - Full summaries, keywords, license
  - `get_document_info` - Returns summary, keywords, license
- **Rust CLI Chat Improvements**:
  - `page [slug] N` - View any page with summary/keywords and image preview
  - `next`/`prev` navigate pages after viewing a page (not just document list)
  - Sources show document slug for easy `page` command usage
  - Sources now show `CHUNK #N` instead of generic `TEXT`
  - `figures`/`tables`/`equations` filter to current page (use `all` suffix for whole doc)
  - Unified citation format: `[1]`, `[2]`, `[3]` everywhere
  - Improved LLM response brevity (2-4 paragraphs)
  - Reorganized help into logical groups (Browse, Elements, View, Search, Other)
  - Piped input support: commands are echoed for test scenario visibility

### Updated Rust CLI
```bash
osgeo-library docs                    # List all documents
osgeo-library docs --page 2           # Paginated list
osgeo-library doc usgs_snyder         # Document details
osgeo-library search "query" -d usgs_snyder  # Search within document
```

### Chat Mode Commands
```
Browse:
  docs              List documents (5 per page)
  doc <N|slug>      View document details
  page [slug] N     View page (e.g., 'page 55' or 'page usgs_snyder 55')
  next/n, prev/p    Navigate pages or document list

Elements:
  figures           List figures on current page (or 'figures all')
  tables            List tables on current page (or 'tables all')
  equations         List equations on current page (or 'equations all')

View:
  show <N>          Show element in terminal
  open <N>          Open element in GUI viewer
  open page <N>     Open page in GUI viewer

Search:
  search <query>    Fast semantic search (no LLM)
  sources           Show sources from last answer
  <question>        Ask a question (uses LLM)
```

---

## 2025-12-29 (v2.1.0)

### New Features
- **Document & Page Summaries**: Enrichment now generates summaries and keywords
  - Page-level: 2-3 sentence summary + 5-8 keywords per page
  - Document-level: 3-5 sentence summary + 10-15 keywords (from page summaries)
  - License extraction from first/last pages
- **Ingest CLI**: `doclibrary ingest` command to load documents into PostgreSQL
  - Supports `--dry-run`, `--skip-existing`, `--delete-first`, `--no-embed`
- **Schema Migration**: New columns for summaries, keywords, license
  - Run: `psql osgeo_library < doclibrary/db/migrations/001_add_summaries.sql`

### Updated Commands
```bash
# Full pipeline
doclibrary extract paper.pdf --pages 1-10 --output-dir db/data/paper
doclibrary enrich paper           # Now includes summaries + keywords
doclibrary ingest paper           # New! Load into database with embeddings
doclibrary search "query"
```

---

## 2025-12-29 (v2.0.0)

Major refactoring: reorganized as `doclibrary` Python package.

### Breaking Changes
- All scripts replaced by unified `doclibrary` CLI
- Configuration now uses `DOCLIBRARY_*` environment variables
- Old standalone scripts archived to `archive/2025-12-29/`
- MCP tools use compound keys (document_slug + element_label) instead of opaque IDs

### New Features
- **Unified CLI**: Single `doclibrary` command with subcommands
  - `doclibrary extract` - Extract elements from PDF
  - `doclibrary enrich` - Generate search_text for elements
  - `doclibrary ingest` - Ingest documents into PostgreSQL database
  - `doclibrary search` - Search from command line
  - `doclibrary chat` - Interactive chat interface
  - `doclibrary serve` - Start REST API server
  - `doclibrary mcp` - Start MCP server for Claude Desktop
  - `doclibrary config` - Show current configuration

- **MCP Server**: Claude Desktop integration via FastMCP (10 tools)
  - Search: `search_documents`, `search_visual_elements`
  - Elements: `get_element_image`, `get_element_details` (compound key lookup)
  - Pages: `get_page_image` (returns native MCP ImageContent)
  - Documents: `get_document_info`, `find_document`, `list_documents`, `list_documents_paginated`
  - Status: `get_library_status`
  - Resource: `tour://library` (usage guide)

- **MCP Image Support**: Image tools return native MCP `ImageContent` type
  - Clients can render images directly as image blocks
  - Equations return rendered LaTeX when available

- **LLM-Friendly Element Lookup**: Compound keys instead of opaque IDs
  - Elements identified by `document_slug` + `element_label`
  - LLM can construct lookup from search results without tracking IDs
  - Optional `page_number` for disambiguation

- **Package Structure**: Proper Python package with submodules
  - `doclibrary.core` - Shared utilities (LLM, text, formatting)
  - `doclibrary.db` - Database operations, chunking
  - `doclibrary.search` - Embedding and search service
  - `doclibrary.extraction` - PDF extraction, enrichment
  - `doclibrary.chat` - Interactive chat interface
  - `doclibrary.servers` - REST API and MCP server

- **Test Suite**: pytest-based tests with markers
  - 68 unit tests (no external dependencies)
  - 11 integration tests (requires postgres, embedding server)
  - Run with `pytest tests/unit/` or `pytest --run-integration`

- **Configuration**: Improved config loading
  - Priority: env vars > config.local.toml > config.toml > ~/.config/doclibrary/
  - `doclibrary config` to display current settings

### Migration Guide

Old commands → New commands:
```bash
python extract_document.py paper.pdf → doclibrary extract paper.pdf
python enrich_elements.py data/      → doclibrary enrich data/
python ingest_to_db.py sam3          → doclibrary ingest sam3
python chat_cli.py                   → doclibrary chat
python server.py                     → doclibrary serve
```

MCP element lookup (new compound key approach):
```python
# Old (opaque ID)
get_element_image(element_id=42)

# New (compound key - LLM-friendly)
get_element_image(document_slug="usgs_snyder", element_label="Table 5")
```

## 2025-12-18 (v0.1.2)

- **CLI `--open` flag**: Open images in GUI viewer (xdg-open/open)
  - Works with SSH tunneling: client runs locally, fetches images over tunnel
  - Available in search command and chat mode (`open N`)
- **Documentation**: Added GUI viewer section to CLIENT.md

## 2025-12-18 (v0.1.1)

- **CLI image rendering improvements**
  - Server returns `rendered_path` and image dimensions in API response
  - Client uses proportional sizing based on terminal dimensions
  - Equations prefer rendered LaTeX images over raw crops
  - Chafa quality options: `--symbols all -w 9 -c full`
- **CLI help improvements**: Added examples and element types list
- **Documentation**: Completed CLIENT.md with troubleshooting and image rendering sections

## 2025-12-16 (evening)

- **db/data structure**: New per-page JSON structure for database ingestion
  - `db/data/{doc}/document.json` - document metadata
  - `db/data/{doc}/pages/page_001.json` - per-page text, elements, timing
  - `db/data/{doc}/images/` - page renders and annotated versions
  - `db/data/{doc}/elements/` - cropped figures, tables, equations
- **migrate_to_db.py**: Converts existing web/data extractions to db/data structure
- **extract_all_pages.py**: Batch extraction of all PDF pages with resumability
  - Skips already-extracted pages (`--skip-existing`)
  - Per-page JSON output (not monolithic)
  - Progress tracking in document.json
- **run_extraction.sh**: Wrapper script for overnight batch runs
- **gitignore**: Added db/data/ (generated content too large for git)

## 2025-12-16

- **LaTeX rendering**: Switched from matplotlib to pdflatex + ImageMagick for full LaTeX support (`align*`, `cases`, matrices)
- **Text cleaning**: Auto-remove margin line numbers from academic papers (ICLR format)
- **New extractions**: USGS Snyder pages 147, 189, 192 (16 equations); Alpine Change pages 7, 8, 12, 16
- **Upgraded model**: Qwen3-VL-32B -> Qwen3-VL-235B for better equation detection
- **Equation pipeline**: Auto-extract LaTeX from model output, render to `*_rendered.png`
- **Filename sanitization**: Remove special chars from element filenames
- **Visual grounding**: New `extract_document.py` using Qwen3-VL bounding boxes (0-1000 scale)
- **Web viewer**: Three-panel layout, document selector, equation dual-display (crop + rendered)
- **Caption-based extraction**: `extract_figures.py` using regex + region rendering
- **Local inference**: Benchmarked Qwen3-VL-8B (~48s/page) vs Qwen2-VL-7B (~180s/page)

## 2025-12-15

- **Initial setup**: Virtual environment, PyMuPDF for text extraction
- **Multimodal testing**: Gemini 2.0 Flash via OpenRouter (rate limited)
- **Comparison website**: Side-by-side viewer for extraction quality evaluation
- **Model comparison**: Tested Nova, Gemma, Nemotron via OpenRouter; Claude as reference
