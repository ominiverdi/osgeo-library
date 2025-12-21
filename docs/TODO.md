# TODO

Actionable tasks for the OSGeo Library project.

## In Progress

- [ ] Matrix bot integration (tools, agent loop, context management)

## Planned

### API Improvements

- [ ] Add `text` field to PageResponse with page full_text
- [ ] Add `elements` field to PageResponse listing elements on that page
- [ ] Add `GET /page/{slug}/{page_number}/annotated` endpoint for annotated images
- [ ] Consider page number mapping (PDF page vs printed page number)

### Search Improvements

- [ ] Evaluate reranker (BGE-reranker) for precision improvement
- [ ] Cross-document weighting (boost results from mentioned document)

### Extraction

- [ ] Process remaining large PDFs (ManualOfDigitalEarth - 846 pages)

## Completed

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
- [x] Document search endpoint
- [x] Page browsing endpoint

## Known Limitations

1. **Page numbers are PDF-based** - `/page/{slug}/1` returns the first PDF page, which may be a cover. Printed page numbers don't match.

2. **No page summary** - Page endpoint returns only image and metadata, not text or element list.

## Open Questions

1. Linked element cap: Return all elements on matching pages, or cap at 5?
2. Chunk size: Is 800 chars with 200 overlap optimal for scientific papers?
