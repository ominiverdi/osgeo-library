#!/usr/bin/env python3
"""
FastAPI server for OSGeo Library.

Provides REST API endpoints for search and chat functionality.
Designed to run as a system service, allowing multi-user access
via a lightweight client (Rust CLI).

Endpoints:
    GET  /health                          - Server status and service checks
    POST /search                          - Semantic search over documents
    POST /chat                            - Search + LLM-powered response
    POST /documents/search                - Search documents by title/slug/filename
    GET  /page/{slug}/{page_number}       - Get page image (base64) with metadata
    GET  /element/{element_id}            - Get element details
    GET  /image/{slug}/{path}             - Serve element images

Usage:
    # Development
    python server.py

    # Production (via uvicorn)
    uvicorn server:app --host 127.0.0.1 --port 8095

Configuration:
    Uses config.toml for all settings (LLM, embedding, database).
    API keys and credentials are kept server-side.
"""

import base64
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image

from config import config
from search_service import (
    search,
    search_elements,
    search_chunks,
    SearchResult,
    _score_from_distance,
    check_server as check_embed_server,
    get_element_by_id,
)

import requests as http_requests

# -----------------------------------------------------------------------------
# App setup
# -----------------------------------------------------------------------------

app = FastAPI(
    title="OSGeo Library API",
    description="Semantic search and chat over scientific documents",
    version="0.1.0",
)

# Allow local connections only (no CORS needed for localhost)
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
    include_elements: bool = Field(
        default=True, description="Include figures/tables/equations"
    )
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
    rendered_path: Optional[str] = None  # For equations: LaTeX-rendered image
    image_width: Optional[int] = None  # Image dimensions for proportional display
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
    conversation_id: Optional[str] = Field(
        default=None, description="For multi-turn (future)"
    )


class ChatResponse(BaseModel):
    """Chat response with answer and sources."""

    answer: str
    sources: List[SearchResultResponse]
    query_used: str  # The actual search query (may be expanded)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    embedding_server: bool
    llm_server: bool
    database: bool
    version: str = "0.1.0"


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
                return img.size  # (width, height)
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
    # Determine best image path and get its dimensions
    best_path = get_best_image_path(r)
    width, height = (
        get_image_dimensions(r.document_slug, best_path) if best_path else (None, None)
    )

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


def check_llm_server() -> bool:
    """Check if LLM server is available."""
    try:
        # Handle OpenRouter vs local server
        if "openrouter" in config.llm_url:
            # OpenRouter - just check if we have an API key
            return bool(config.llm_api_key)
        else:
            # Local server - check health endpoint
            health_url = config.llm_url.replace("/v1/chat/completions", "/health")
            response = http_requests.get(health_url, timeout=5)
            return response.status_code == 200
    except http_requests.exceptions.RequestException:
        return False


def check_database() -> bool:
    """Check if database is accessible."""
    try:
        from db.connection import fetch_one

        result = fetch_one("SELECT 1")
        return result is not None
    except Exception:
        return False


def get_source_tag(result: SearchResult) -> str:
    """Get short tag for source type."""
    type_map = {
        "chunk": "t",
        "figure": "f",
        "table": "tb",
        "equation": "eq",
        "chart": "ch",
        "diagram": "d",
    }
    if result.source_type == "element":
        return type_map.get(result.element_type or "", "e")
    return "t"


def format_context_for_llm(results: List[SearchResult]) -> str:
    """Format search results as context for LLM."""
    if not results:
        return "No relevant documents found."

    parts = []
    for i, r in enumerate(results, 1):
        tag = get_source_tag(r)
        if r.source_type == "element":
            element_type = (r.element_type or "element").upper()
            parts.append(
                f"[{tag}:{i}] {element_type}: {r.element_label} "
                f"(from {r.document_title}, page {r.page_number})\n"
                f"    {r.content[:500]}"
            )
        else:
            parts.append(
                f"[{tag}:{i}] TEXT (from {r.document_title}, page {r.page_number})\n"
                f"    {r.content[:500]}"
            )

    return "\n\n".join(parts)


def query_llm(messages: List[dict], model: str = "") -> str:
    """Send messages to LLM and get response."""
    if not model:
        model = config.llm_model

    try:
        headers = {"Content-Type": "application/json"}
        if config.llm_api_key:
            headers["Authorization"] = f"Bearer {config.llm_api_key}"

        response = http_requests.post(
            config.llm_url,
            json={
                "model": model,
                "messages": messages,
                "temperature": config.llm_temperature,
                "max_tokens": config.llm_max_tokens,
            },
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        # Remove thinking tags if present (Qwen3 /think mode)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")


# System prompt for chat
SYSTEM_PROMPT = """You are a helpful research assistant with access to a library of scientific documents about:
- Map projections and cartography (USGS Snyder manual)
- Computer vision and segmentation (SAM3 paper)
- Alpine habitat monitoring and change detection

When answering questions:
1. Base your answers ONLY on the provided context
2. Be concise but accurate
3. ALWAYS cite sources using the exact tags from the context:
   - [f:N] for figures
   - [tb:N] for tables  
   - [eq:N] for equations
   - [t:N] for text passages
4. If the context doesn't contain enough information, say so

Do not make up information. Always include citation tags in your response."""


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check server and dependency status."""
    embed_ok = check_embed_server()
    llm_ok = check_llm_server()
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
    """
    Semantic search over documents.

    Returns ranked results from text chunks and/or elements (figures, tables, equations).
    """
    if not check_embed_server():
        raise HTTPException(status_code=503, detail="Embedding server unavailable")

    try:
        # Route to appropriate search function
        if req.element_type:
            results = search_elements(
                req.query,
                limit=req.limit,
                document_slug=req.document_slug,
                element_type=req.element_type,
            )
        elif not req.include_chunks:
            results = search_elements(
                req.query,
                limit=req.limit,
                document_slug=req.document_slug,
            )
        elif not req.include_elements:
            results = search_chunks(
                req.query,
                limit=req.limit,
                document_slug=req.document_slug,
            )
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


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Ask a question and get an LLM-powered answer with citations.

    Performs semantic search, builds context, and queries the LLM.
    Returns the answer along with source references.
    """
    if not check_embed_server():
        raise HTTPException(status_code=503, detail="Embedding server unavailable")

    if not check_llm_server():
        raise HTTPException(status_code=503, detail="LLM server unavailable")

    try:
        # Search for relevant content
        results = search(
            req.question,
            limit=req.limit,
            document_slug=req.document_slug,
        )

        # Build context for LLM
        context = format_context_for_llm(results)

        # Create the augmented prompt
        augmented_question = f"""Context (cite using the tags shown):

{context}

Question: {req.question}

IMPORTANT: Include citation tags like [f:1], [t:2], [eq:3], [tb:4] in your answer to reference the sources above."""

        # Query LLM
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": augmented_question},
        ]

        answer = query_llm(messages)

        return ChatResponse(
            answer=answer,
            sources=[result_to_response(r) for r in results],
            query_used=req.question,
        )

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/element/{element_id}")
async def get_element(element_id: int):
    """Get full details for a specific element."""
    element = get_element_by_id(element_id)
    if not element:
        raise HTTPException(status_code=404, detail="Element not found")

    # Convert to dict, handling any non-serializable fields
    result = dict(element)
    # Remove embedding vector (too large for API response)
    result.pop("embedding", None)
    return result


@app.get("/image/{document_slug}/{path:path}")
async def get_image(document_slug: str, path: str):
    """
    Serve element images.

    Path format: /image/{document_slug}/elements/{filename}
    Example: /image/usgs_snyder/elements/p51_figure_1_FIGURE_7.png
    """
    # Sanitize path to prevent directory traversal
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    # Build full path
    full_path = Path(config.data_dir) / document_slug / path

    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {path}")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    # Check it's an image
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


@app.post("/documents/search", response_model=DocumentSearchResponse)
async def search_documents(req: DocumentSearchRequest):
    """
    Search documents by title, slug, or source filename.

    Returns matching documents with their slugs and page counts.
    """
    from db.connection import fetch_all

    try:
        # Case-insensitive search on title, slug, and source_file
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
    """
    Get a page image with metadata.

    Returns base64-encoded image and document info including total pages.
    """
    from db.connection import fetch_one, fetch_all

    try:
        # Get document info
        doc = fetch_one(
            "SELECT id, slug, title FROM documents WHERE slug = %s",
            (document_slug,),
        )
        if not doc:
            raise HTTPException(
                status_code=404, detail=f"Document not found: {document_slug}"
            )

        # Get total page count
        page_count = fetch_one(
            "SELECT COUNT(*) as total FROM pages WHERE document_id = %s",
            (doc["id"],),
        )
        total_pages = page_count["total"] if page_count else 0

        # Get the specific page
        page = fetch_one(
            """
            SELECT page_number, image_path, annotated_image_path, width, height
            FROM pages
            WHERE document_id = %s AND page_number = %s
            """,
            (doc["id"], page_number),
        )
        if not page:
            raise HTTPException(
                status_code=404,
                detail=f"Page {page_number} not found. Document has {total_pages} pages.",
            )

        # Load and encode the image
        image_path = Path(config.data_dir) / document_slug / page["image_path"]
        if not image_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Image file not found: {page['image_path']}"
            )

        with open(image_path, "rb") as f:
            image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        # Determine mime type
        suffix = image_path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        mime_type = mime_types.get(suffix, "image/png")

        # Get dimensions (from DB or image)
        width = page["width"]
        height = page["height"]
        if not width or not height:
            with Image.open(image_path) as img:
                width, height = img.size

        # Check if annotated version exists
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

    print("Starting OSGeo Library API server...")
    print(f"Config source: {config.config_source}")
    print(f"Embedding server: {config.embed_url}")
    print(f"LLM: {config.llm_model} @ {config.llm_url}")
    print()

    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=8095,
        reload=False,  # Set to True for development
        log_level="info",
    )
