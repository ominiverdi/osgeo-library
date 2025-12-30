# API Reference

REST API and MCP server for doclibrary.

## REST API

**Start server:** `doclibrary serve --port 8095`

**Base URL:** `http://localhost:8095`

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server status and dependency checks |
| `/search` | POST | Semantic search over documents |
| `/chat` | POST | Search + LLM-powered response |
| `/documents` | GET | List all documents (paginated, with summaries) |
| `/documents/{slug}` | GET | Get document details with summary/keywords |
| `/documents/search` | POST | Search documents by title/slug/filename |
| `/page/{slug}/{page}` | GET | Get page image with metadata and summary |
| `/element/{id}` | GET | Get element details by ID |
| `/image/{slug}/{path}` | GET | Serve element images |

---

### GET /health

Check server and dependency status.

**Response:**
```json
{
    "status": "healthy",
    "embedding_server": true,
    "database": true,
    "version": "2.0.0"
}
```

---

### GET /search

Semantic search over documents.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | Search query text |
| `limit` | int | 10 | Max results (1-50) |
| `document` | string | null | Filter by document slug |
| `type` | string | null | Filter: "figure", "table", "equation", "chunk" |

**Example:** `GET /search?q=map+projection&limit=5`

**Response:**
```json
{
    "query": "map projection",
    "results": [
        {
            "id": 123,
            "score": 0.85,
            "content": "The Transverse Mercator projection...",
            "source_type": "chunk",
            "document_slug": "usgs_snyder",
            "document_title": "Map Projections: A Working Manual",
            "page_number": 42,
            "element_type": null,
            "element_label": null,
            "crop_path": null
        }
    ],
    "total": 5
}
```

---

### POST /search

Alternative search with JSON body.

**Request:**
```json
{
    "query": "oblique mercator equations",
    "limit": 10,
    "document_slug": null,
    "include_chunks": true,
    "include_elements": true,
    "element_type": null
}
```

---

### GET /documents

List all documents with pagination. Includes summaries and keywords.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 20 | Results per page (1-100) |
| `sort_by` | string | "title" | Sort: "title", "date_added", "page_count" |

**Example:** `GET /documents?page=1&page_size=10&sort_by=title`

**Response:**
```json
{
    "documents": [
        {
            "slug": "usgs_snyder",
            "title": "Map Projections: A Working Manual",
            "source_file": "snyder_1987.pdf",
            "total_pages": 397,
            "summary": "This manual provides a comprehensive treatment of map projections...",
            "keywords": ["map projection", "cartography", "geodesy", "coordinate systems"],
            "license": "Public Domain"
        }
    ],
    "page": 1,
    "page_size": 10,
    "total_pages": 1,
    "total_documents": 10
}
```

---

### GET /documents/{slug}

Get detailed information about a specific document.

**Example:** `GET /documents/usgs_snyder`

**Response:**
```json
{
    "slug": "usgs_snyder",
    "title": "Map Projections: A Working Manual",
    "source_file": "snyder_1987.pdf",
    "total_pages": 397,
    "summary": "This manual provides a comprehensive treatment of map projections...",
    "keywords": ["map projection", "cartography", "geodesy", "coordinate systems"],
    "license": "Public Domain",
    "extraction_date": "2024-12-20",
    "element_counts": {
        "figures": 45,
        "tables": 23,
        "equations": 156,
        "diagrams": 12,
        "charts": 5
    }
}
```

---

### GET /elements/{id}

Get full details for a specific element.

**Example:** `GET /elements/42`

**Response:**
```json
{
    "id": 42,
    "element_type": "equation",
    "label": "Equation 5-9",
    "description": "Spherical trigonometry formula for latitude",
    "search_text": "The sine of latitude phi equals...",
    "latex": "\\sin \\phi = \\sin \\phi_1 \\cos c + ...",
    "document_slug": "usgs_snyder",
    "document_title": "Map Projections: A Working Manual",
    "page_number": 26,
    "crop_path": "elements/p26_equation_1_Equation_5-9.png",
    "rendered_path": "elements/p26_equation_1_Equation_5-9_rendered.png"
}
```

---

### Error Responses

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
| 503 | Service unavailable (embedding server down) |

---

## MCP Server

Model Context Protocol server for Claude Desktop integration.

**Start server:** `doclibrary mcp`

### Configuration

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "doclibrary": {
      "command": "doclibrary",
      "args": ["mcp"]
    }
  }
}
```

Or with explicit Python path:

```json
{
  "mcpServers": {
    "doclibrary": {
      "command": "python",
      "args": ["-m", "doclibrary.servers.mcp"],
      "cwd": "/path/to/osgeo-library"
    }
  }
}
```

### Available Tools

See [MCP_SERVER_SPEC.md](MCP_SERVER_SPEC.md) for complete tool documentation.

#### Search Tools

| Tool | Description |
|------|-------------|
| `search_documents` | Semantic search over all content |
| `search_visual_elements` | Search figures, tables, equations |

#### Element Tools (Compound Key)

Elements are identified by `document_slug` + `element_label` (not opaque IDs):

| Tool | Description |
|------|-------------|
| `get_element_image` | Get element as ImageContent |
| `get_element_details` | Get element text details |

#### Page & Document Tools

| Tool | Description |
|------|-------------|
| `get_page_image` | Get page as ImageContent |
| `get_document_info` | Get document metadata |
| `find_document` | Find document by partial name |
| `list_documents` | List all documents |
| `list_documents_paginated` | List with pagination |
| `get_library_status` | Check service health |

**Returns:** Text and ImageContent for image tools, JSON for metadata tools.

---

#### search_visual_elements

Search specifically for visual elements (figures, tables, equations, diagrams).

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Search query text |
| `element_type` | string | no | Filter: "figure", "table", "equation", "diagram", "chart" |
| `limit` | int | no | Max results (default: 10) |

**Returns:** List of matching elements with type, label, and description.

---

#### get_element_details

Get detailed information about a specific element by ID.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `element_id` | int | yes | Element ID from search results |

**Returns:** Full element details including description, LaTeX (for equations), and file paths.

---

#### list_documents

List all documents available in the library.

**Parameters:** None

**Returns:** List of documents with titles, slugs, and statistics.

---

#### get_library_status

Check the status of the library service.

**Parameters:** None

**Returns:** Status of database connection and embedding server availability.

---

### Example Usage in Claude

After configuring the MCP server, you can ask Claude:

> "Search my document library for information about map projections"

Claude will use the `search_documents` tool to query your library and return relevant results.

> "Find all equations related to the Mercator projection"

Claude will use `search_visual_elements` with `element_type: "equation"`.

> "What documents are in my library?"

Claude will use `list_documents` to show available documents.
