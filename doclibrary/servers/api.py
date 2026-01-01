#!/usr/bin/env python3
"""
FastAPI server for doclibrary.

Provides REST API endpoints for search and chat functionality.
Designed to run as a system service, allowing multi-user access
via a lightweight client (Rust CLI).

Endpoints:
    GET  /health                          - Server status and service checks
    POST /search                          - Semantic search over documents
    POST /chat                            - Search + LLM-powered response
    GET  /documents                       - List all documents (paginated)
    GET  /documents/{slug}                - Get document details with summary/keywords
    GET  /documents/{slug}/elements       - List elements with optional filtering
    POST /documents/search                - Search documents by title/slug/filename
    GET  /page/{slug}/{page_number}       - Get page image (base64) with metadata
    GET  /element/{element_id}            - Get element details
    GET  /image/{slug}/{path}             - Serve element images

Usage:
    # Development
    python -m doclibrary.servers.api

    # Production (via uvicorn)
    uvicorn doclibrary.servers.api:app --host 127.0.0.1 --port 8095

Configuration:
    Uses config.toml for all settings (LLM, embedding, database).
    API keys and credentials are kept server-side.
"""

import base64
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

from doclibrary.config import config
from doclibrary.core.constants import SYSTEM_PROMPT
from doclibrary.core.formatting import format_context_for_llm
from doclibrary.core.llm import check_llm_health, query_llm
from doclibrary.db import fetch_all, fetch_one, get_document_by_slug
from doclibrary.search import (
    SearchResult,
    check_server as check_embed_server,
    get_element_by_id,
    search,
    search_chunks,
    search_elements,
)
from doclibrary.search.service import _score_from_distance

# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------

app = FastAPI(
    title="doclibrary API",
    description="Semantic search and chat over scientific documents",
    version="1.0.0",
)

# Allow local connections only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Request/Response models
# -----------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Search request parameters."""

    query: str = Field(..., description="Search query text")
    limit: int = Field(default=10, ge=1, le=50, description="Max results")
    document_slug: Optional[str] = Field(default=None, description="Filter by document")
    include_chunks: bool = Field(default=True, description="Include text chunks")
    include_elements: bool = Field(default=True, description="Include figures/tables/equations")
    element_type: Optional[str] = Field(default=None, description="Filter element type")


class SearchResultResponse(BaseModel):
    """Single search result."""

    id: int
    score_pct: float = Field(description="Relevance score (0-100%)")
    content: str
    source_type: str  # 'chunk' or 'element'
    document_slug: str
    document_title: str
    page_number: int
    # Element-specific
    element_type: Optional[str] = None
    element_label: Optional[str] = None
    crop_path: Optional[str] = None
    rendered_path: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    # Chunk-specific
    chunk_index: Optional[int] = None


class SearchResponse(BaseModel):
    """Search response with results."""

    query: str
    results: List[SearchResultResponse]
    total: int


class ChatRequest(BaseModel):
    """Chat request parameters."""

    question: str = Field(..., description="User question")
    limit: int = Field(default=8, ge=1, le=20, description="Max context results")
    document_slug: Optional[str] = Field(default=None, description="Filter by document")
    conversation_id: Optional[str] = Field(default=None, description="For multi-turn (future)")


class ChatResponse(BaseModel):
    """Chat response with answer and sources."""

    answer: str
    sources: List[SearchResultResponse]
    query_used: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    embedding_server: bool
    llm_server: bool
    database: bool
    version: str = "1.0.0"


class DocumentSearchRequest(BaseModel):
    """Document search request parameters."""

    query: str = Field(..., description="Search query for title/slug/filename")
    limit: int = Field(default=20, ge=1, le=100, description="Max results")


class DocumentSearchResult(BaseModel):
    """Single document search result."""

    slug: str
    title: str
    source_file: str
    total_pages: int


class DocumentSearchResponse(BaseModel):
    """Document search response."""

    query: str
    results: List[DocumentSearchResult]
    total: int


class DocumentListItem(BaseModel):
    """Document item in list response."""

    slug: str
    title: str
    source_file: Optional[str] = None
    total_pages: int
    summary: Optional[str] = None
    keywords: Optional[List[str]] = None
    license: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Paginated document list response."""

    documents: List[DocumentListItem]
    page: int
    page_size: int
    total_pages: int
    total_documents: int


class DocumentDetailResponse(BaseModel):
    """Full document details response."""

    slug: str
    title: str
    source_file: Optional[str] = None
    total_pages: int
    summary: Optional[str] = None
    keywords: Optional[List[str]] = None
    license: Optional[str] = None
    extraction_date: Optional[str] = None
    element_counts: dict = Field(default_factory=dict)


class PageResponse(BaseModel):
    """Page image and metadata response."""

    document_slug: str
    document_title: str
    page_number: int
    total_pages: int
    image_base64: str
    image_width: int
    image_height: int
    mime_type: str = "image/png"
    has_annotated: bool = False
    summary: Optional[str] = None
    keywords: Optional[List[str]] = None


class ElementListItem(BaseModel):
    """Single element in list response."""

    id: int
    element_type: str
    label: Optional[str] = None
    page_number: int
    description: Optional[str] = None
    crop_path: Optional[str] = None
    rendered_path: Optional[str] = None


class ElementListResponse(BaseModel):
    """Paginated element list response."""

    document_slug: str
    elements: List[ElementListItem]
    total: int
    limit: int
    offset: int


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------


def get_image_dimensions(
    document_slug: str, image_path: str
) -> Tuple[Optional[int], Optional[int]]:
    """Get image width and height. Returns (None, None) if image not found."""
    if not image_path:
        return None, None
    try:
        full_path = Path(config.data_dir) / document_slug / image_path
        if full_path.exists():
            with Image.open(full_path) as img:
                return img.size
    except Exception:
        pass
    return None, None


def get_best_image_path(r: SearchResult) -> Optional[str]:
    """Get the best image path for display. Prefers rendered_path for equations."""
    if r.element_type == "equation" and r.rendered_path:
        return r.rendered_path
    return r.crop_path


def result_to_response(r: SearchResult) -> SearchResultResponse:
    """Convert internal SearchResult to API response."""
    best_path = get_best_image_path(r)
    width, height = get_image_dimensions(r.document_slug, best_path) if best_path else (None, None)

    return SearchResultResponse(
        id=r.id,
        score_pct=round(_score_from_distance(r.score), 1),
        content=r.content or "",
        source_type=r.source_type,
        document_slug=r.document_slug,
        document_title=r.document_title,
        page_number=r.page_number,
        element_type=r.element_type,
        element_label=r.element_label,
        crop_path=r.crop_path,
        rendered_path=r.rendered_path,
        image_width=width,
        image_height=height,
        chunk_index=r.chunk_index,
    )


def check_database() -> bool:
    """Check if database is accessible."""
    try:
        result = fetch_one("SELECT 1")
        return result is not None
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check server and dependency status."""
    embed_ok = check_embed_server()
    llm_ok = check_llm_health(config.llm_url)
    db_ok = check_database()

    status = "healthy" if (embed_ok and llm_ok and db_ok) else "degraded"

    return HealthResponse(
        status=status,
        embedding_server=embed_ok,
        llm_server=llm_ok,
        database=db_ok,
    )


@app.post("/search", response_model=SearchResponse)
async def search_endpoint(req: SearchRequest):
    """Semantic search over documents."""
    if not check_embed_server():
        raise HTTPException(status_code=503, detail="Embedding server unavailable")

    try:
        if req.element_type:
            results = search_elements(
                req.query,
                limit=req.limit,
                document_slug=req.document_slug,
                element_type=req.element_type,
            )
        elif not req.include_chunks:
            results = search_elements(req.query, limit=req.limit, document_slug=req.document_slug)
        elif not req.include_elements:
            results = search_chunks(req.query, limit=req.limit, document_slug=req.document_slug)
        else:
            results = search(
                req.query,
                limit=req.limit,
                document_slug=req.document_slug,
                include_chunks=req.include_chunks,
                include_elements=req.include_elements,
            )

        return SearchResponse(
            query=req.query,
            results=[result_to_response(r) for r in results],
            total=len(results),
        )

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


def extract_search_terms(question: str, document_info: Optional[dict] = None) -> str:
    """Use LLM to extract effective search terms from a natural language question.

    This enables multi-pass search: first extract what to search for,
    then perform the actual search. More robust than direct keyword extraction,
    especially for conversational queries and multilingual environments.

    Args:
        question: The user's natural language question
        document_info: Optional dict with 'title', 'summary', 'keywords' for context

    Returns:
        Space-separated search terms optimized for hybrid search
    """
    context_section = ""
    if document_info:
        title = document_info.get("title", "")
        summary = document_info.get("summary", "")
        keywords = document_info.get("keywords", [])
        if isinstance(keywords, list):
            keywords = ", ".join(keywords)

        context_section = f"""
Document context:
- Title: {title}
- Summary: {summary[:300]}{"..." if len(summary) > 300 else ""}
- Keywords: {keywords}

"""

    prompt = f"""Extract 3-6 effective search terms from this question.
{context_section}
Rules:
- Return only the key terms, space-separated
- Focus on nouns, technical terms, and specific concepts
- Use domain-specific terms from the document context when relevant
- Remove conversational filler (can you, please, tell me, etc.)
- Keep proper nouns and acronyms
- No explanation, just the terms

Question: {question}

Search terms:"""

    messages = [{"role": "user", "content": prompt}]

    # Use lower temperature for consistent extraction
    terms = query_llm(
        messages,
        config.llm_url,
        config.llm_model,
        api_key=config.llm_api_key,
        temperature=0.1,
        max_tokens=50,
    )

    # Clean up: remove quotes, extra punctuation, newlines
    terms = terms.strip().strip("\"'").replace("\n", " ")

    # Fallback to original question if extraction fails
    if not terms or terms.startswith("Error"):
        return question

    return terms


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Ask a question and get an LLM-powered answer with citations."""
    if not check_embed_server():
        raise HTTPException(status_code=503, detail="Embedding server unavailable")

    if not check_llm_health(config.llm_url):
        raise HTTPException(status_code=503, detail="LLM server unavailable")

    try:
        # Fetch document context if a document is selected
        document_info = None
        if req.document_slug:
            document_info = get_document_by_slug(req.document_slug)

        # Pass 1: Extract search terms from natural language question
        search_terms = extract_search_terms(req.question, document_info)

        # Pass 2: Search with extracted terms (scoped to document if selected)
        results = search(search_terms, limit=req.limit, document_slug=req.document_slug)

        # Fallback: If no results and a document was selected, search all documents
        used_fallback = False
        if not results and req.document_slug:
            results = search(search_terms, limit=req.limit, document_slug=None)
            used_fallback = True

        context = format_context_for_llm(results)

        # Note in question if using fallback results
        fallback_note = ""
        if used_fallback and results:
            fallback_note = f"\n\nNote: No results were found in '{req.document_slug}', showing results from other documents."

        augmented_question = f"""Context (cite using the tags shown):

{context}{fallback_note}

Question: {req.question}

IMPORTANT: Include citation tags like [1], [2], [3] in your answer to reference the sources above. Do NOT include a references/sources list at the end - just cite inline."""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": augmented_question},
        ]

        # Pass 3: Generate answer
        answer = query_llm(messages, config.llm_url, config.llm_model, api_key=config.llm_api_key)

        # Include fallback info in query_used
        query_info = search_terms
        if used_fallback:
            query_info = f"{search_terms} (fallback: all docs)"

        return ChatResponse(
            answer=answer,
            sources=[result_to_response(r) for r in results],
            query_used=query_info,
        )

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/element/{element_id}")
async def get_element(element_id: int):
    """Get full details for a specific element."""
    element = get_element_by_id(element_id)
    if not element:
        raise HTTPException(status_code=404, detail="Element not found")

    result = dict(element)
    result.pop("embedding", None)
    return result


@app.get("/image/{document_slug}/{path:path}")
async def get_image(document_slug: str, path: str):
    """Serve element images."""
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    full_path = Path(config.data_dir) / document_slug / path

    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {path}")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    suffix = full_path.suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        raise HTTPException(status_code=400, detail="Not an image file")

    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    return FileResponse(full_path, media_type=media_types.get(suffix, "image/png"))


@app.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "title",
):
    """List all documents with pagination.

    Args:
        page: Page number (1-indexed, default: 1)
        page_size: Results per page (default: 20, max: 100)
        sort_by: Sort field: 'title', 'date_added', or 'page_count'
    """
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
        total_pages = (total_docs + page_size - 1) // page_size if total_docs > 0 else 0

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

        return DocumentListResponse(
            documents=[
                DocumentListItem(
                    slug=r["slug"],
                    title=r["title"],
                    source_file=r["source_file"],
                    total_pages=r["page_count"],
                    summary=r["summary"],
                    keywords=r["keywords"],
                    license=r["license"],
                )
                for r in results
            ],
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            total_documents=total_docs,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents/{document_slug}", response_model=DocumentDetailResponse)
async def get_document(document_slug: str):
    """Get detailed information about a specific document.

    Returns document metadata including summary, keywords, license,
    and element counts by type.
    """
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
            raise HTTPException(status_code=404, detail=f"Document '{document_slug}' not found")

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

        return DocumentDetailResponse(
            slug=doc["slug"],
            title=doc["title"],
            source_file=doc.get("source_file"),
            total_pages=doc["page_count"],
            summary=doc.get("summary"),
            keywords=doc.get("keywords"),
            license=doc.get("license"),
            extraction_date=str(doc["extraction_date"]) if doc.get("extraction_date") else None,
            element_counts={
                "figures": elements["figures"] if elements else 0,
                "tables": elements["tables"] if elements else 0,
                "equations": elements["equations"] if elements else 0,
                "diagrams": elements["diagrams"] if elements else 0,
                "charts": elements["charts"] if elements else 0,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents/{document_slug}/elements", response_model=ElementListResponse)
async def list_elements(
    document_slug: str,
    element_type: Optional[str] = None,
    page: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List elements from a document with optional filtering.

    Args:
        document_slug: Document identifier
        element_type: Filter by type: figure, table, equation, chart, diagram
        page: Filter to elements on a specific page (1-indexed)
        limit: Maximum results (default: 50, max: 100)
        offset: Pagination offset (default: 0)

    Returns:
        List of elements with metadata (no embedding vectors)
    """
    try:
        # Validate limit
        limit = min(max(1, limit), 100)
        offset = max(0, offset)

        # Get document
        doc = fetch_one("SELECT id, slug FROM documents WHERE slug = %s", (document_slug,))
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document '{document_slug}' not found")

        # Build query with filters
        conditions = ["e.document_id = %s"]
        params: list = [doc["id"]]

        if element_type:
            valid_types = {"figure", "table", "equation", "chart", "diagram"}
            if element_type.lower() not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid element_type. Must be one of: {', '.join(sorted(valid_types))}",
                )
            conditions.append("e.element_type = %s")
            params.append(element_type.lower())

        if page is not None:
            if page < 1:
                raise HTTPException(status_code=400, detail="Page must be >= 1")
            conditions.append("p.page_number = %s")
            params.append(page)

        where_clause = " AND ".join(conditions)

        # Get total count (need join for page filter)
        total_result = fetch_one(
            f"""SELECT COUNT(*) as count 
                FROM elements e
                JOIN pages p ON e.page_id = p.id
                WHERE {where_clause}""",
            tuple(params),
        )
        total = total_result["count"] if total_result else 0

        # Get elements with page number from pages table
        params.extend([limit, offset])
        results = fetch_all(
            f"""SELECT e.id, e.element_type, e.label, p.page_number, 
                       e.search_text as description, e.crop_path, e.rendered_path
                FROM elements e
                JOIN pages p ON e.page_id = p.id
                WHERE {where_clause}
                ORDER BY p.page_number, e.label
                LIMIT %s OFFSET %s""",
            tuple(params),
        )

        return ElementListResponse(
            document_slug=document_slug,
            elements=[
                ElementListItem(
                    id=r["id"],
                    element_type=r["element_type"],
                    label=r["label"],
                    page_number=r["page_number"],
                    description=r["description"][:200] if r["description"] else None,
                    crop_path=r["crop_path"],
                    rendered_path=r["rendered_path"],
                )
                for r in results
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/documents/search", response_model=DocumentSearchResponse)
async def search_documents(req: DocumentSearchRequest):
    """Search documents by title, slug, or source filename."""
    try:
        query_pattern = f"%{req.query}%"
        results = fetch_all(
            """
            SELECT 
                d.slug,
                d.title,
                d.source_file,
                COUNT(p.id) as total_pages
            FROM documents d
            LEFT JOIN pages p ON p.document_id = d.id
            WHERE d.title ILIKE %s
               OR d.slug ILIKE %s
               OR d.source_file ILIKE %s
            GROUP BY d.id, d.slug, d.title, d.source_file
            ORDER BY d.title
            LIMIT %s
            """,
            (query_pattern, query_pattern, query_pattern, req.limit),
        )

        return DocumentSearchResponse(
            query=req.query,
            results=[
                DocumentSearchResult(
                    slug=r["slug"],
                    title=r["title"],
                    source_file=r["source_file"],
                    total_pages=r["total_pages"],
                )
                for r in results
            ],
            total=len(results),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/page/{document_slug}/{page_number}", response_model=PageResponse)
async def get_page(document_slug: str, page_number: int):
    """Get a page image with metadata."""
    try:
        doc = fetch_one("SELECT id, slug, title FROM documents WHERE slug = %s", (document_slug,))
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found: {document_slug}")

        page_count = fetch_one(
            "SELECT COUNT(*) as total FROM pages WHERE document_id = %s", (doc["id"],)
        )
        total_pages = page_count["total"] if page_count else 0

        page = fetch_one(
            "SELECT page_number, image_path, annotated_image_path, width, height, summary, keywords FROM pages WHERE document_id = %s AND page_number = %s",
            (doc["id"], page_number),
        )
        if not page:
            raise HTTPException(
                status_code=404,
                detail=f"Page {page_number} not found. Document has {total_pages} pages.",
            )

        image_path = Path(config.data_dir) / document_slug / page["image_path"]
        if not image_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Image file not found: {page['image_path']}"
            )

        with open(image_path, "rb") as f:
            image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        suffix = image_path.suffix.lower()
        mime_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        mime_type = mime_types.get(suffix, "image/png")

        width = page["width"]
        height = page["height"]
        if not width or not height:
            with Image.open(image_path) as img:
                width, height = img.size

        has_annotated = bool(page["annotated_image_path"])

        return PageResponse(
            document_slug=doc["slug"],
            document_title=doc["title"],
            page_number=page["page_number"],
            total_pages=total_pages,
            image_base64=image_base64,
            image_width=width,
            image_height=height,
            mime_type=mime_type,
            has_annotated=has_annotated,
            summary=page.get("summary"),
            keywords=page.get("keywords"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn

    print("Starting doclibrary API server...")
    print(f"Config source: {config.config_source}")
    print(f"Embedding server: {config.embed_url}")
    print(f"LLM: {config.llm_model} @ {config.llm_url}")
    print()

    uvicorn.run(
        "doclibrary.servers.api:app",
        host="127.0.0.1",
        port=8095,
        reload=False,
        log_level="info",
    )
