#!/usr/bin/env python3
"""
MCP (Model Context Protocol) server for doclibrary.

Exposes document search and retrieval functionality as MCP tools that can be
used by AI assistants like Claude Desktop.

Usage:
    # Run directly
    python -m doclibrary.servers.mcp

    # Or via CLI
    doclibrary mcp

Configuration for Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "doclibrary": {
          "command": "python",
          "args": ["-m", "doclibrary.servers.mcp"]
        }
      }
    }

Available Tools:
    - search_documents: Semantic search over document library
    - search_visual_elements: Search figures, tables, equations (requires embedding server)
    - list_elements: Browse elements by document/type/page (no embedding needed)
    - get_element_details: Get details for a specific element by ID
    - get_element_image: Get element image as base64
    - get_page_image: Get full page image as base64
    - get_document_info: Get document metadata
    - find_document: Find document by name/query
    - list_documents: List all documents (paginated)
    - get_library_status: Check service status
"""

import base64
import logging
import sys
from pathlib import Path
from typing import Any

# Configure logging to stderr (required for STDIO MCP servers)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("doclibrary.mcp")

# Import MCP SDK
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ImageContent, TextContent
except ImportError:
    logger.error("MCP SDK not installed. Install with: pip install 'mcp[cli]'")
    sys.exit(1)

from doclibrary.config import config
from doclibrary.search import (
    SearchResult,
    check_server as check_embed_server,
    get_element_by_id,
    search,
    search_elements,
)
from doclibrary.search.service import _score_from_distance

# Initialize FastMCP server
mcp = FastMCP("doclibrary")


def format_search_result(result: SearchResult, index: int) -> str:
    """Format a search result for display.

    Includes document_slug and element_label so LLM can call get_element_image
    with compound key (no need to track opaque IDs).
    """
    score_pct = _score_from_distance(result.score)

    if result.source_type == "element":
        elem_type = (result.element_type or "element").upper()
        return f"""[{index}] {elem_type}: {result.element_label}
  Document: {result.document_slug}
  Page: {result.page_number}
  Score: {score_pct:.1f}%
  Content: {result.content[:300]}..."""
    else:
        return f"""[{index}] TEXT CHUNK
  Document: {result.document_slug}
  Page: {result.page_number}
  Score: {score_pct:.1f}%
  Content: {result.content[:300]}..."""


@mcp.tool()
async def search_documents(
    query: str,
    limit: int = 10,
    document_slug: str | None = None,
) -> str:
    """Search the document library for relevant content.

    Performs hybrid semantic and keyword search over text chunks and
    visual elements (figures, tables, equations, diagrams).

    Args:
        query: Search query text (e.g., "oblique mercator projection equations")
        limit: Maximum number of results to return (1-50, default 10)
        document_slug: Optional filter to search only within a specific document
    """
    if not check_embed_server():
        return "Error: Embedding server not available. Cannot perform search."

    try:
        results = search(
            query=query,
            limit=min(max(1, limit), 50),
            document_slug=document_slug,
        )

        if not results:
            return f"No results found for query: {query}"

        formatted = [f"Found {len(results)} results for: {query}\n"]
        for i, result in enumerate(results, 1):
            formatted.append(format_search_result(result, i))

        return "\n\n".join(formatted)

    except Exception as e:
        logger.error(f"Search error: {e}")
        return f"Search error: {e}"


@mcp.tool()
async def search_visual_elements(
    query: str,
    element_type: str | None = None,
    limit: int = 10,
    document_slug: str | None = None,
) -> str:
    """Search for visual elements (figures, tables, equations, diagrams, charts).

    Use this when looking for specific types of visual content like:
    - Figures and diagrams explaining concepts
    - Tables with data or comparisons
    - Mathematical equations and formulas
    - Charts and graphs

    Args:
        query: Search query text
        element_type: Filter by type: 'figure', 'table', 'equation', 'diagram', 'chart'
        limit: Maximum number of results (1-50, default 10)
        document_slug: Optional filter to specific document
    """
    if not check_embed_server():
        return "Error: Embedding server not available. Cannot perform search."

    try:
        results = search_elements(
            query=query,
            limit=min(max(1, limit), 50),
            document_slug=document_slug,
            element_type=element_type,
        )

        if not results:
            type_filter = f" of type '{element_type}'" if element_type else ""
            return f"No visual elements{type_filter} found for query: {query}"

        formatted = [f"Found {len(results)} visual elements for: {query}\n"]
        for i, result in enumerate(results, 1):
            formatted.append(format_search_result(result, i))

        return "\n\n".join(formatted)

    except Exception as e:
        logger.error(f"Search elements error: {e}")
        return f"Search error: {e}"


@mcp.tool()
async def list_elements(
    document_slug: str,
    element_type: str | None = None,
    page: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List visual elements from a document without requiring a search query.

    Use this to browse elements (figures, tables, equations) in a document.
    Unlike search_visual_elements, this doesn't require the embedding server.

    Args:
        document_slug: Document identifier (e.g., 'usgs_snyder', 'torchgeo')
        element_type: Filter by type: 'figure', 'table', 'equation', 'diagram', 'chart'
        page: Filter to elements on a specific page (1-indexed)
        limit: Maximum results (1-50, default 20)
        offset: Pagination offset (default 0)

    Returns:
        Dictionary with elements list and pagination info
    """
    from doclibrary.db import fetch_all, fetch_one

    try:
        # Validate inputs
        limit = min(max(1, limit), 50)
        offset = max(0, offset)

        # Get document
        doc = fetch_one("SELECT id, slug, title FROM documents WHERE slug = %s", (document_slug,))
        if not doc:
            return {"error": f"Document '{document_slug}' not found"}

        # Build query with filters
        conditions = ["e.document_id = %s"]
        params: list = [doc["id"]]

        if element_type:
            valid_types = {"figure", "table", "equation", "chart", "diagram"}
            if element_type.lower() not in valid_types:
                return {
                    "error": f"Invalid element_type. Must be one of: {', '.join(sorted(valid_types))}"
                }
            conditions.append("e.element_type = %s")
            params.append(element_type.lower())

        if page is not None:
            if page < 1:
                return {"error": "Page must be >= 1"}
            conditions.append("p.page_number = %s")
            params.append(page)

        where_clause = " AND ".join(conditions)

        # Get total count
        total_result = fetch_one(
            f"""SELECT COUNT(*) as count 
                FROM elements e
                JOIN pages p ON e.page_id = p.id
                WHERE {where_clause}""",
            tuple(params),
        )
        total = total_result["count"] if total_result else 0

        # Get elements
        params.extend([limit, offset])
        results = fetch_all(
            f"""SELECT e.id, e.element_type, e.label, p.page_number, 
                       e.search_text as description, e.crop_path
                FROM elements e
                JOIN pages p ON e.page_id = p.id
                WHERE {where_clause}
                ORDER BY p.page_number, e.label
                LIMIT %s OFFSET %s""",
            tuple(params),
        )

        return {
            "document_slug": document_slug,
            "document_title": doc["title"],
            "elements": [
                {
                    "id": r["id"],
                    "element_type": r["element_type"],
                    "label": r["label"],
                    "page_number": r["page_number"],
                    "description": r["description"][:150] + "..."
                    if r["description"] and len(r["description"]) > 150
                    else r["description"],
                }
                for r in results
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "hint": "Use get_element_image(document_slug, element_label) to view an element",
        }

    except Exception as e:
        logger.error(f"List elements error: {e}")
        return {"error": f"Error listing elements: {e}"}


@mcp.tool()
async def get_element_details(
    document_slug: str,
    element_label: str,
    page_number: int | None = None,
) -> str:
    """Get detailed text information about an element.

    Look up element by document and label. Use page_number to disambiguate
    if multiple elements have the same label.

    Args:
        document_slug: Document identifier (e.g., 'usgs_snyder', 'torchgeo')
        element_label: Element label from search results (e.g., 'Table 5', 'Figure 3-1')
        page_number: Optional page number to disambiguate if multiple matches
    """
    from doclibrary.db import fetch_one

    try:
        # Build query based on provided parameters
        if page_number:
            element = fetch_one(
                """SELECT e.*, d.slug as document_slug, d.title as document_title, p.page_number
                   FROM elements e
                   JOIN documents d ON e.document_id = d.id
                   JOIN pages p ON e.page_id = p.id
                   WHERE d.slug = %s AND e.label = %s AND p.page_number = %s
                   LIMIT 1""",
                (document_slug, element_label, page_number),
            )
        else:
            element = fetch_one(
                """SELECT e.*, d.slug as document_slug, d.title as document_title, p.page_number
                   FROM elements e
                   JOIN documents d ON e.document_id = d.id
                   JOIN pages p ON e.page_id = p.id
                   WHERE d.slug = %s AND e.label = %s
                   LIMIT 1""",
                (document_slug, element_label),
            )

        if not element:
            msg = f"Element '{element_label}' not found in document '{document_slug}'"
            if page_number:
                msg += f" on page {page_number}"
            return f"Error: {msg}."

        # Format element details
        lines = [
            f"Type: {element.get('element_type', 'unknown').upper()}",
            f"Label: {element.get('label', 'N/A')}",
            f"Document: {element.get('document_title', 'Unknown')} ({document_slug})",
            f"Page: {element.get('page_number', 'N/A')}",
            "",
            "Description:",
            element.get("description", "No description available"),
        ]

        if element.get("search_text"):
            lines.extend(["", "Context:", element["search_text"]])

        if element.get("latex"):
            lines.extend(["", "LaTeX:", element["latex"]])

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Get element error: {e}")
        return f"Error retrieving element: {e}"


@mcp.tool()
async def list_documents() -> str:
    """List all available documents in the library with summaries.

    Returns a list of documents with their slugs, titles, page counts,
    and brief summaries. Use the slug to filter searches or get more
    details with get_document_info.
    """
    from doclibrary.db import fetch_all

    try:
        results = fetch_all(
            """
            SELECT d.slug, d.title, d.summary, COUNT(p.id) as page_count
            FROM documents d
            LEFT JOIN pages p ON p.document_id = d.id
            GROUP BY d.id, d.slug, d.title, d.summary
            ORDER BY d.title
            """
        )

        if not results:
            return "No documents found in the library."

        lines = ["Available documents:\n"]
        for doc in results:
            lines.append(f"## {doc['title']} ({doc['slug']})")
            lines.append(f"   Pages: {doc['page_count']}")
            if doc.get("summary"):
                # Truncate long summaries for list view
                summary = doc["summary"]
                if len(summary) > 200:
                    summary = summary[:200] + "..."
                lines.append(f"   Summary: {summary}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"List documents error: {e}")
        return f"Error listing documents: {e}"


@mcp.tool()
async def get_library_status() -> str:
    """Check the status of the document library services.

    Returns information about:
    - Embedding server status
    - Database connection
    - Configuration source
    """
    from doclibrary.db import fetch_one

    status_lines = ["Document Library Status\n"]

    # Check embedding server
    embed_ok = check_embed_server()
    status_lines.append(f"Embedding server: {'OK' if embed_ok else 'NOT AVAILABLE'}")
    status_lines.append(f"  URL: {config.embed_url}")

    # Check database
    try:
        result = fetch_one("SELECT COUNT(*) as doc_count FROM documents")
        doc_count = result["doc_count"] if result else 0
        status_lines.append(f"Database: OK ({doc_count} documents)")
    except Exception as e:
        status_lines.append(f"Database: ERROR - {e}")

    status_lines.append(f"Config source: {config.config_source}")

    return "\n".join(status_lines)


# --- New tools from MCP_SERVER_SPEC.md ---


@mcp.tool()
async def get_page_image(document_slug: str, page_number: int) -> list:
    """Get a full page as an image.

    Use this to view a specific page of a document.
    Returns both the image (for Claude Desktop) and a cached file path (for chat bridges).

    Args:
        document_slug: Document identifier (e.g., 'usgs_snyder')
        page_number: Page number (1-indexed)

    Returns:
        List containing TextContent (metadata + cache path) and ImageContent (for direct display)
    """
    import shutil
    import tempfile
    from doclibrary.db import fetch_one

    try:
        # Get document info
        doc = fetch_one("SELECT id, title FROM documents WHERE slug = %s", (document_slug,))
        if not doc:
            return [TextContent(type="text", text=f"Error: Document '{document_slug}' not found.")]

        # Get total pages
        total = fetch_one(
            "SELECT COUNT(*) as count FROM pages WHERE document_id = %s", (doc["id"],)
        )
        total_pages = total["count"] if total else 0

        if page_number < 1 or page_number > total_pages:
            return [
                TextContent(
                    type="text",
                    text=f"Error: Page {page_number} not found. Document has {total_pages} pages.",
                )
            ]

        # Get page image path
        page = fetch_one(
            """SELECT image_path, width, height FROM pages 
               WHERE document_id = %s AND page_number = %s""",
            (doc["id"], page_number),
        )
        if not page or not page.get("image_path"):
            return [
                TextContent(type="text", text=f"Error: Page {page_number} image not available.")
            ]

        # Source image path
        image_path = Path(config.data_dir) / document_slug / page["image_path"]
        if not image_path.exists():
            return [
                TextContent(type="text", text=f"Error: Page image file not found: {image_path}")
            ]

        # Copy to cache directory (for chat bridges that can't receive base64)
        cache_dir = Path(tempfile.gettempdir()) / "doclibrary_cache"
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / f"{document_slug}_page{page_number}.png"
        shutil.copy2(image_path, cache_file)

        # Read and encode image (for Claude Desktop and other MCP clients)
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Return metadata (with cache path) + image
        metadata = f"""Page {page_number} of {total_pages}
Document: {doc["title"]} ({document_slug})
Size: {page.get("width", "?")}x{page.get("height", "?")} pixels
Image file: {cache_file}"""

        return [
            TextContent(type="text", text=metadata),
            ImageContent(type="image", data=image_data, mimeType="image/png"),
        ]

    except Exception as e:
        logger.error(f"Get page image error: {e}")
        return [TextContent(type="text", text=f"Error retrieving page: {e}")]


@mcp.tool()
async def get_element_image(
    document_slug: str,
    element_label: str,
    page_number: int | None = None,
) -> list:
    """Get an element's image (figure, table, equation).

    Look up element by document and label. Use page_number to disambiguate
    if multiple elements have the same label.

    For equations, returns the rendered LaTeX image if available.
    Returns both the image (for Claude Desktop) and a cached file path (for chat bridges).

    Args:
        document_slug: Document identifier (e.g., 'usgs_snyder', 'torchgeo')
        element_label: Element label from search results (e.g., 'Table 5', 'Figure 3-1')
        page_number: Optional page number to disambiguate if multiple matches

    Returns:
        List containing TextContent (metadata + cache path) and ImageContent (for direct display)
    """
    import re
    import shutil
    import tempfile
    from doclibrary.db import fetch_one

    try:
        # Build query based on provided parameters
        if page_number:
            element = fetch_one(
                """SELECT e.*, d.slug as document_slug, d.title as document_title, p.page_number
                   FROM elements e
                   JOIN documents d ON e.document_id = d.id
                   JOIN pages p ON e.page_id = p.id
                   WHERE d.slug = %s AND e.label = %s AND p.page_number = %s
                   LIMIT 1""",
                (document_slug, element_label, page_number),
            )
        else:
            element = fetch_one(
                """SELECT e.*, d.slug as document_slug, d.title as document_title, p.page_number
                   FROM elements e
                   JOIN documents d ON e.document_id = d.id
                   JOIN pages p ON e.page_id = p.id
                   WHERE d.slug = %s AND e.label = %s
                   LIMIT 1""",
                (document_slug, element_label),
            )

        if not element:
            msg = f"Element '{element_label}' not found in document '{document_slug}'"
            if page_number:
                msg += f" on page {page_number}"
            return [TextContent(type="text", text=f"Error: {msg}.")]

        # Prefer rendered path for equations, fall back to crop path
        image_rel_path = element.get("rendered_path") or element.get("crop_path")
        if not image_rel_path:
            return [
                TextContent(type="text", text=f"Error: No image available for '{element_label}'.")
            ]

        # Build full path
        image_path = Path(config.data_dir) / document_slug / image_rel_path
        if not image_path.exists():
            return [TextContent(type="text", text=f"Error: Image file not found: {image_path}")]

        # Copy to cache directory (for chat bridges that can't receive base64)
        cache_dir = Path(tempfile.gettempdir()) / "doclibrary_cache"
        cache_dir.mkdir(exist_ok=True)
        # Sanitize label for filename
        safe_label = re.sub(r"[^\w\-]", "_", element_label)
        cache_file = cache_dir / f"{document_slug}_{safe_label}.png"
        shutil.copy2(image_path, cache_file)

        # Read and encode image (for Claude Desktop and other MCP clients)
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Format metadata
        elem_type = (element.get("element_type") or "element").upper()
        label = element.get("label", "N/A")
        doc_title = element.get("document_title", "Unknown")
        page_num = element.get("page_number", "?")
        description = element.get("description", "")

        metadata = f"""{elem_type}: {label}
Document: {doc_title} ({document_slug})
Page: {page_num}
{description[:200] + "..." if len(description) > 200 else description}
Image file: {cache_file}"""

        return [
            TextContent(type="text", text=metadata),
            ImageContent(type="image", data=image_data, mimeType="image/png"),
        ]

    except Exception as e:
        logger.error(f"Get element image error: {e}")
        return [TextContent(type="text", text=f"Error retrieving element image: {e}")]


# --- Lightweight path-only tools for chat bridges ---


@mcp.tool()
async def get_page_path(document_slug: str, page_number: int) -> str:
    """Get a page image as a cached file path (lightweight, no base64 encoding).

    Use this for chat bridges that can't receive images via MCP protocol.
    The image is copied to a cache directory and the path is returned.

    Args:
        document_slug: Document identifier (e.g., 'usgs_snyder')
        page_number: Page number (1-indexed)

    Returns:
        Text with metadata and path to the cached image file
    """
    import shutil
    import tempfile
    from doclibrary.db import fetch_one

    try:
        # Get document info
        doc = fetch_one("SELECT id, title FROM documents WHERE slug = %s", (document_slug,))
        if not doc:
            return f"Error: Document '{document_slug}' not found."

        # Get total pages
        total = fetch_one(
            "SELECT COUNT(*) as count FROM pages WHERE document_id = %s", (doc["id"],)
        )
        total_pages = total["count"] if total else 0

        if page_number < 1 or page_number > total_pages:
            return f"Error: Page {page_number} not found. Document has {total_pages} pages."

        # Get page image path
        page = fetch_one(
            """SELECT image_path, width, height FROM pages 
               WHERE document_id = %s AND page_number = %s""",
            (doc["id"], page_number),
        )
        if not page or not page.get("image_path"):
            return f"Error: Page {page_number} image not available."

        # Source image path
        image_path = Path(config.data_dir) / document_slug / page["image_path"]
        if not image_path.exists():
            return f"Error: Page image file not found: {image_path}"

        # Copy to cache directory
        cache_dir = Path(tempfile.gettempdir()) / "doclibrary_cache"
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / f"{document_slug}_page{page_number}.png"
        shutil.copy2(image_path, cache_file)

        # Return metadata with cache path (no base64 encoding)
        return f"""Page {page_number} of {total_pages}
Document: {doc["title"]} ({document_slug})
Size: {page.get("width", "?")}x{page.get("height", "?")} pixels
Image file: {cache_file}"""

    except Exception as e:
        logger.error(f"Get page path error: {e}")
        return f"Error retrieving page: {e}"


@mcp.tool()
async def get_element_path(
    document_slug: str,
    element_label: str,
    page_number: int | None = None,
) -> str:
    """Get an element image as a cached file path (lightweight, no base64 encoding).

    Use this for chat bridges that can't receive images via MCP protocol.
    The image is copied to a cache directory and the path is returned.

    Args:
        document_slug: Document identifier (e.g., 'usgs_snyder', 'torchgeo')
        element_label: Element label from search results (e.g., 'Table 5', 'Figure 3-1')
        page_number: Optional page number to disambiguate if multiple matches

    Returns:
        Text with metadata and path to the cached image file
    """
    import re
    import shutil
    import tempfile
    from doclibrary.db import fetch_one

    try:
        # Build query based on provided parameters
        if page_number:
            element = fetch_one(
                """SELECT e.*, d.slug as document_slug, d.title as document_title, p.page_number
                   FROM elements e
                   JOIN documents d ON e.document_id = d.id
                   JOIN pages p ON e.page_id = p.id
                   WHERE d.slug = %s AND e.label = %s AND p.page_number = %s
                   LIMIT 1""",
                (document_slug, element_label, page_number),
            )
        else:
            element = fetch_one(
                """SELECT e.*, d.slug as document_slug, d.title as document_title, p.page_number
                   FROM elements e
                   JOIN documents d ON e.document_id = d.id
                   JOIN pages p ON e.page_id = p.id
                   WHERE d.slug = %s AND e.label = %s
                   LIMIT 1""",
                (document_slug, element_label),
            )

        if not element:
            msg = f"Element '{element_label}' not found in document '{document_slug}'"
            if page_number:
                msg += f" on page {page_number}"
            return f"Error: {msg}."

        # Prefer rendered path for equations, fall back to crop path
        image_rel_path = element.get("rendered_path") or element.get("crop_path")
        if not image_rel_path:
            return f"Error: No image available for '{element_label}'."

        # Build full path
        image_path = Path(config.data_dir) / document_slug / image_rel_path
        if not image_path.exists():
            return f"Error: Image file not found: {image_path}"

        # Copy to cache directory
        cache_dir = Path(tempfile.gettempdir()) / "doclibrary_cache"
        cache_dir.mkdir(exist_ok=True)
        # Sanitize label for filename
        safe_label = re.sub(r"[^\w\-]", "_", element_label)
        cache_file = cache_dir / f"{document_slug}_{safe_label}.png"
        shutil.copy2(image_path, cache_file)

        # Format metadata (no base64 encoding)
        elem_type = (element.get("element_type") or "element").upper()
        label = element.get("label", "N/A")
        doc_title = element.get("document_title", "Unknown")
        page_num = element.get("page_number", "?")
        description = element.get("description", "")

        return f"""{elem_type}: {label}
Document: {doc_title} ({document_slug})
Page: {page_num}
{description[:200] + "..." if len(description) > 200 else description}
Image file: {cache_file}"""

    except Exception as e:
        logger.error(f"Get element path error: {e}")
        return f"Error retrieving element: {e}"


@mcp.tool()
async def get_document_info(document_slug: str) -> dict:
    """Get detailed metadata about a document.

    Use this to get page count, element counts, summary, keywords, and license.

    Args:
        document_slug: Document identifier (e.g., 'usgs_snyder')

    Returns:
        Dictionary with document metadata including:
        - slug, title, source_file, total_pages
        - summary: 3-5 sentence document summary
        - keywords: list of topic keywords
        - license: extracted license information
        - indexed_elements: counts by type (figures, tables, equations, etc.)
    """
    from doclibrary.db import fetch_one

    try:
        doc = fetch_one(
            """SELECT d.*, COUNT(DISTINCT p.id) as page_count
               FROM documents d
               LEFT JOIN pages p ON p.document_id = d.id
               WHERE d.slug = %s
               GROUP BY d.id""",
            (document_slug,),
        )
        if not doc:
            return {"error": f"Document '{document_slug}' not found."}

        # Get element counts by type
        elements = fetch_one(
            """SELECT 
                 COUNT(*) FILTER (WHERE element_type = 'figure') as figures,
                 COUNT(*) FILTER (WHERE element_type = 'table') as tables,
                 COUNT(*) FILTER (WHERE element_type = 'equation') as equations,
                 COUNT(*) FILTER (WHERE element_type = 'diagram') as diagrams,
                 COUNT(*) FILTER (WHERE element_type = 'chart') as charts
               FROM elements WHERE document_id = %s""",
            (doc["id"],),
        )

        return {
            "slug": doc["slug"],
            "title": doc["title"],
            "source_file": doc.get("source_file"),
            "total_pages": doc["page_count"],
            "summary": doc.get("summary"),
            "keywords": doc.get("keywords"),
            "license": doc.get("license"),
            "indexed_elements": {
                "figures": elements["figures"] if elements else 0,
                "tables": elements["tables"] if elements else 0,
                "equations": elements["equations"] if elements else 0,
                "diagrams": elements["diagrams"] if elements else 0,
                "charts": elements["charts"] if elements else 0,
            },
        }

    except Exception as e:
        logger.error(f"Get document info error: {e}")
        return {"error": f"Error retrieving document info: {e}"}


@mcp.tool()
async def find_document(query: str, limit: int = 5) -> dict:
    """Find documents by name, title, or filename.

    Use this to resolve partial names to document slugs.
    E.g., "snyder" -> "usgs_snyder"

    Args:
        query: Search query (matches title, slug, or source_file)
        limit: Maximum results (default: 5)

    Returns:
        Dictionary with matching documents
    """
    from doclibrary.db import fetch_all

    try:
        # Search in slug, title, and source_file
        pattern = f"%{query}%"
        results = fetch_all(
            """SELECT d.slug, d.title, d.source_file, COUNT(p.id) as total_pages
               FROM documents d
               LEFT JOIN pages p ON p.document_id = d.id
               WHERE d.slug ILIKE %s OR d.title ILIKE %s OR d.source_file ILIKE %s
               GROUP BY d.id
               ORDER BY d.title
               LIMIT %s""",
            (pattern, pattern, pattern, limit),
        )

        return {
            "results": [
                {
                    "slug": r["slug"],
                    "title": r["title"],
                    "source_file": r["source_file"],
                    "total_pages": r["total_pages"],
                }
                for r in results
            ],
            "total_count": len(results),
        }

    except Exception as e:
        logger.error(f"Find document error: {e}")
        return {"error": f"Error finding document: {e}"}


@mcp.tool()
async def list_documents_paginated(
    page: int = 1, page_size: int = 20, sort_by: str = "title"
) -> dict:
    """List all documents with pagination, including summaries and keywords.

    Args:
        page: Page number (1-indexed, default: 1)
        page_size: Results per page (default: 20, max: 100)
        sort_by: Sort field: 'title', 'date_added', or 'page_count'

    Returns:
        Dictionary with documents (including summary, keywords, license) and pagination info
    """
    from doclibrary.db import fetch_all, fetch_one

    try:
        # Validate inputs
        page = max(1, page)
        page_size = min(max(1, page_size), 100)

        # Map sort field
        sort_map = {
            "title": "d.title",
            "date_added": "d.extraction_date DESC",
            "page_count": "page_count DESC",
        }
        order_by = sort_map.get(sort_by, "d.title")

        # Get total count
        total = fetch_one("SELECT COUNT(*) as count FROM documents")
        total_docs = total["count"] if total else 0
        total_pages = (total_docs + page_size - 1) // page_size

        # Get page of results with summaries and keywords
        offset = (page - 1) * page_size
        results = fetch_all(
            f"""SELECT d.slug, d.title, d.source_file, d.summary, d.keywords, d.license,
                       COUNT(p.id) as page_count
                FROM documents d
                LEFT JOIN pages p ON p.document_id = d.id
                GROUP BY d.id
                ORDER BY {order_by}
                LIMIT %s OFFSET %s""",
            (page_size, offset),
        )

        return {
            "documents": [
                {
                    "slug": r["slug"],
                    "title": r["title"],
                    "source_file": r["source_file"],
                    "total_pages": r["page_count"],
                    "summary": r.get("summary"),
                    "keywords": r.get("keywords"),
                    "license": r.get("license"),
                }
                for r in results
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total_documents": total_docs,
            },
        }

    except Exception as e:
        logger.error(f"List documents error: {e}")
        return {"error": f"Error listing documents: {e}"}


@mcp.resource("tour://library")
def get_library_tour() -> str:
    """Library usage guide and tour."""
    return """# OSGeo Document Library

Welcome to the OSGeo Document Library! This library contains scientific documents 
about geospatial topics including map projections, remote sensing, and GIS.

## Searching

Use these tools to find content:

- `search_documents` - Search all content (text and visual elements)
- `search_visual_elements` - Search specifically for figures, tables, equations
- `find_document` - Find a document by partial name (e.g., "snyder")

## Viewing Content

After searching, use these tools to view results:

- `get_element_image` - Get a figure, table, or equation as an image
- `get_page_image` - Get a full page as an image
- `get_element_details` - Get text description of an element

## Document Navigation

- `list_documents` - See all available documents
- `get_document_info` - Get details about a specific document
- `get_library_status` - Check if all services are running

## Example Workflow

1. Search: `search_visual_elements("mercator projection diagram")`
2. View result: `get_element_image(42)` (using ID from search)
3. See full page: `get_page_image("usgs_snyder", 51)`

## Tips

- Use document_slug to filter searches to one document
- Element IDs are numeric (from search results)
- Page numbers are 1-indexed
"""


def main():
    """Run the MCP server."""
    logger.info("Starting doclibrary MCP server...")
    logger.info(f"Config source: {config.config_source}")

    # Run the server with STDIO transport
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
