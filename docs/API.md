# API Reference

REST API for the OSGeo Library server.

**Base URL:** `http://localhost:8095`

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server status and dependency checks |
| `/search` | POST | Semantic search over documents |
| `/chat` | POST | Search + LLM-powered response |
| `/documents/search` | POST | Search documents by title/slug/filename |
| `/page/{slug}/{page_number}` | GET | Get page image (base64) with metadata |
| `/element/{id}` | GET | Get element details by ID |
| `/image/{slug}/{path}` | GET | Serve element images |

---

## GET /health

Check server and dependency status.

**Response:**
```json
{
    "status": "healthy",
    "embedding_server": true,
    "llm_server": true,
    "database": true,
    "version": "0.1.0"
}
```

Status is "healthy" if all dependencies are up, "degraded" otherwise.

---

## POST /search

Semantic search over documents. Returns ranked results from text chunks and/or elements.

**Request:**
```json
{
    "query": "map projection equations",
    "limit": 10,
    "document_slug": null,
    "include_chunks": true,
    "include_elements": true,
    "element_type": null
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | required | Search query text |
| `limit` | int | 10 | Max results (1-50) |
| `document_slug` | string | null | Filter by document |
| `include_chunks` | bool | true | Include text chunks |
| `include_elements` | bool | true | Include figures/tables/equations |
| `element_type` | string | null | Filter: "figure", "table", "equation" |

**Response:**
```json
{
    "query": "map projection equations",
    "results": [
        {
            "id": 123,
            "score_pct": 85.3,
            "content": "The forward equations for the...",
            "source_type": "chunk",
            "document_slug": "usgs_snyder",
            "document_title": "Map Projections: A Working Manual",
            "page_number": 42,
            "element_type": null,
            "element_label": null,
            "crop_path": null,
            "rendered_path": null,
            "image_width": null,
            "image_height": null,
            "chunk_index": 3
        }
    ],
    "total": 10
}
```

---

## POST /chat

Ask a question and get an LLM-powered answer with citations.

**Request:**
```json
{
    "question": "What is the UTM projection?",
    "limit": 8,
    "document_slug": null
}
```

**Response:**
```json
{
    "answer": "The Universal Transverse Mercator (UTM) projection is...[t:1][eq:2]",
    "sources": [...],
    "query_used": "What is the UTM projection?"
}
```

Sources array contains the same structure as `/search` results. Citation tags in the answer (e.g., `[t:1]`, `[eq:2]`) reference sources by index.

---

## POST /documents/search

Search for documents by title, slug, or source filename.

**Request:**
```json
{
    "query": "snyder",
    "limit": 20
}
```

**Response:**
```json
{
    "query": "snyder",
    "results": [
        {
            "slug": "usgs_snyder",
            "title": "Map Projections: A Working Manual",
            "source_file": "snyder_1987.pdf",
            "total_pages": 397
        }
    ],
    "total": 1
}
```

---

## GET /page/{slug}/{page_number}

Get a page image with metadata. Returns base64-encoded image data.

**Example:** `GET /page/usgs_snyder/26`

**Response:**
```json
{
    "document_slug": "usgs_snyder",
    "document_title": "Map Projections: A Working Manual",
    "page_number": 26,
    "total_pages": 397,
    "image_base64": "iVBORw0KGgo...",
    "image_width": 1322,
    "image_height": 1655,
    "mime_type": "image/png",
    "has_annotated": true
}
```

**Errors:**
- `404`: Document not found
- `404`: Page out of bounds (message includes total page count)

---

## GET /element/{id}

Get full details for a specific element.

**Example:** `GET /element/42`

**Response:**
```json
{
    "id": 42,
    "document_id": 1,
    "page_id": 26,
    "element_type": "equation",
    "label": "Equation 5-9",
    "description": "LaTeX: \\sin \\phi = ...",
    "search_text": "Spherical trigonometry equation...",
    "latex": "\\sin \\phi = ...",
    "crop_path": "elements/p26_equation_1_Equation_5-9.png",
    "rendered_path": "elements/p26_equation_1_Equation_5-9_rendered.png",
    "bbox_pixels": [100, 200, 500, 300]
}
```

---

## GET /image/{slug}/{path}

Serve element images as binary files.

**Example:** `GET /image/usgs_snyder/elements/p26_equation_1_Equation_5-9.png`

Returns the image file with appropriate MIME type.

---

## Error Responses

All endpoints return errors in this format:

```json
{
    "detail": "Error message here"
}
```

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid parameters) |
| 404 | Resource not found |
| 500 | Internal server error |
| 502 | LLM error (for /chat) |
| 503 | Service unavailable (embedding/LLM server down) |
