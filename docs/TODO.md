# TODO

Actionable tasks for the doclibrary project.

## Planned

### API Improvements

- [ ] Add pagination to search results
- [ ] Add `elements` field to document endpoint listing all elements
- [ ] WebSocket support for streaming chat responses

### Search Improvements

- [ ] Evaluate reranker (BGE-reranker) for precision improvement
- [ ] Cross-document weighting (boost results from mentioned document)
- [ ] Query expansion using LLM
- [ ] Search by keywords (use page/document keywords for filtering)

### MCP Server

- [ ] Add `get_page` tool for page content retrieval
- [ ] Add `chat` tool for multi-turn conversations
- [ ] Add resource URIs for elements

### Testing

- [ ] Add more unit tests for chat module
- [ ] Add unit tests for extraction module (with mocked LLM)
- [ ] Set up CI/CD with GitHub Actions

## Completed (v2.2.0)

- [x] REST API: GET /documents (paginated) with summaries, keywords, license
- [x] REST API: GET /documents/{slug} with element counts
- [x] REST API: Page endpoint includes summary/keywords
- [x] MCP Server: Expose document/page summaries in tools
- [x] Rust CLI: `docs` command with pagination
- [x] Rust CLI: `doc <slug>` command for document details
- [x] Rust CLI chat: `docs`, `doc`, `figures`, `tables`, `equations`, `search` commands
- [x] Rust CLI chat: Source navigation with `show N`/`open N`
- [x] Unified citation format: simple [1], [2], [3] tags
- [x] Improved LLM response brevity (concise 2-4 paragraph answers)

## Completed (v2.1.0)

- [x] Database ingestion CLI command (`doclibrary ingest`)
- [x] Document summaries and keywords (LLM-generated)
- [x] Page summaries and keywords (LLM-generated)
- [x] License extraction from documents
- [x] Schema migration for new fields
- [x] Process all documents including large PDFs (digital_earth 844 pages, usgs_snyder 397 pages)

## Completed (v2.0.0)

- [x] Refactor to `doclibrary` Python package
- [x] Unified CLI with subcommands
- [x] MCP server for Claude Desktop
- [x] Configuration from TOML + env vars
- [x] Test suite with pytest markers
- [x] Updated documentation

## Completed (v0.x)

- [x] PostgreSQL + pgvector schema
- [x] BGE-M3 embedding generation
- [x] Element enrichment with Qwen3-30B
- [x] Text chunking with sentence breaks
- [x] Full ingestion pipeline
- [x] Semantic search service
- [x] Hybrid search (semantic + BM25)
- [x] FastAPI REST server
- [x] Rust CLI client
- [x] Deploy to osgeo7-gallery

## Known Limitations

1. **Page numbers are PDF-based** - Page 1 is the first PDF page, which may be a cover. Printed page numbers may not match.

2. **No streaming** - Chat responses are returned as complete text, not streamed.

3. **Single database** - Currently only supports one PostgreSQL database at a time.

4. **Pages with <100 chars skip summarization** - Title pages, blank pages, and image-only pages don't get summaries.
