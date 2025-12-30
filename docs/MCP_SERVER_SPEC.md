# MCP Server Specification: doclibrary

## Overview

This document specifies the MCP tools provided by the doclibrary server. The server is **stateless** - all session state (caching, navigation) is handled client-side.

---

## Element Identification: Compound Keys

Elements are identified using **compound keys** (document_slug + element_label) rather than opaque IDs. This is LLM-friendly because the LLM can construct the lookup parameters directly from search results.

**Search result shows:**
```
[1] TABLE: Table 5
  Document: torchgeo
  Page: 9
```

**LLM calls:**
```python
get_element_image(
    document_slug="torchgeo",
    element_label="Table 5"
)
```

Use `page_number` to disambiguate if multiple elements share the same label.

---

## Implemented Tools

### Search Tools

#### `search_documents`
Semantic search over all content (text chunks and visual elements).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Search query text |
| `limit` | int | no | Max results (default: 10, max: 50) |
| `document_slug` | string | no | Filter to specific document |

**Returns:** Formatted text with results including document_slug and element_label for follow-up calls.

---

#### `search_visual_elements`
Search specifically for figures, tables, equations, diagrams, charts.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Search query text |
| `element_type` | string | no | Filter: 'figure', 'table', 'equation', 'diagram', 'chart' |
| `limit` | int | no | Max results (default: 10) |
| `document_slug` | string | no | Filter to specific document |

---

### Element Tools

#### `get_element_image`
Get an element's image. Returns MCP `ImageContent` for direct rendering.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_slug` | string | yes | Document identifier (e.g., 'usgs_snyder') |
| `element_label` | string | yes | Element label (e.g., 'Table 5', 'Figure 3-1') |
| `page_number` | int | no | Disambiguate if multiple matches |

**Returns:** List of `[TextContent, ImageContent]` - metadata and PNG image.

For equations, automatically returns rendered LaTeX image if available.

---

#### `get_element_details`
Get detailed text information about an element.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_slug` | string | yes | Document identifier |
| `element_label` | string | yes | Element label |
| `page_number` | int | no | Disambiguate if multiple matches |

**Returns:** Text with type, label, description, context, and LaTeX (for equations).

---

### Page Tools

#### `get_page_image`
Get a full page as an image. Returns MCP `ImageContent`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_slug` | string | yes | Document identifier |
| `page_number` | int | yes | Page number (1-indexed) |

**Returns:** List of `[TextContent, ImageContent]` - page info and PNG image.

---

### Document Tools

#### `get_document_info`
Get document metadata including element counts.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `document_slug` | string | yes | Document identifier |

**Returns:** JSON with slug, title, total_pages, indexed_elements counts.

---

#### `find_document`
Find documents by partial name match.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Search query (matches slug, title, filename) |
| `limit` | int | no | Max results (default: 5) |

**Returns:** JSON with matching documents.

---

#### `list_documents`
List all documents (simple version).

**Returns:** Formatted text list of all documents with slugs and page counts.

---

#### `list_documents_paginated`
List documents with pagination.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `page` | int | no | Page number (default: 1) |
| `page_size` | int | no | Results per page (default: 20, max: 100) |
| `sort_by` | string | no | 'title', 'date_added', or 'page_count' |

**Returns:** JSON with documents array and pagination info.

---

#### `get_library_status`
Check service health.

**Returns:** Text with embedding server status, database status, config source.

---

## MCP Resource

#### `tour://library`
Static resource with library usage guide and tips.

---

## Image Responses

Image tools (`get_page_image`, `get_element_image`) return native MCP content types:

```python
[
    TextContent(type="text", text="Page 1 of 397\nDocument: ..."),
    ImageContent(type="image", data="<base64>", mimeType="image/png")
]
```

Clients can render `ImageContent` directly as image blocks.

---

## Error Handling

Errors are returned as `TextContent` with message starting with "Error:":

```python
[TextContent(type="text", text="Error: Document 'xyz' not found.")]
```

---

## Client-Side Responsibilities

The client handles:

- **Result caching** - Store search results per session
- **Navigation state** - Track current page/document
- **Document resolution** - Use `find_document` to resolve partial names
- **Result formatting** - Format for LLM consumption

---

## Example Workflow

1. **Search:** `search_visual_elements("mercator projection diagram")`
2. **View image:** `get_element_image(document_slug="usgs_snyder", element_label="Figure 8-1")`
3. **Get details:** `get_element_details(document_slug="usgs_snyder", element_label="Figure 8-1")`
4. **See full page:** `get_page_image(document_slug="usgs_snyder", page_number=51)`

---

## Configuration

MCP client configuration:

```json
{
  "mcpServers": {
    "doclibrary": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "doclibrary.servers.mcp"],
      "cwd": "/path/to/osgeo-library"
    }
  }
}
```
