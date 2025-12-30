#!/usr/bin/env python3
"""
Semantic search service for doclibrary.

Searches both text chunks and extracted elements (figures, tables, equations)
using vector similarity with pgvector.

Usage:
    from doclibrary.search import search, search_elements, search_chunks

    # Search everything
    results = search("oblique mercator projection equations")

    # Search only elements (figures, tables, equations)
    elements = search_elements("map projection diagram", element_type="figure")

    # Search only text chunks
    chunks = search_chunks("coordinate transformation")
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from doclibrary.core.constants import STOPWORDS
from doclibrary.core.text import extract_keywords
from doclibrary.db import fetch_all, fetch_one
from doclibrary.search.embeddings import check_server, get_embedding


# Score thresholds for filtering results
# See docs/DECISIONS.md for details on threshold tuning
#
# DISTANCE_THRESHOLD: maximum distance to include (filters out irrelevant results)
# - 0.985 allows entity/name searches that semantic search struggles with
#
# MIN_CONFIDENCE_PCT: minimum confidence to return results
# - Filters out low-relevance semantic matches that don't contain query terms
# - 30% filters noise while keeping partial matches
# - Example: "glacier monitoring" at 15% confidence has neither word
#
SCORE_THRESHOLD_PCT = 5
DISTANCE_THRESHOLD = 1.0 - (SCORE_THRESHOLD_PCT / 100 * 0.3)  # 0.985

MIN_CONFIDENCE_PCT = 20
MIN_CONFIDENCE_DISTANCE = 1.0 - (MIN_CONFIDENCE_PCT / 100 * 0.3)  # 0.94


def _score_from_distance(distance: float) -> float:
    """Convert L2 distance to percentage score (0-100)."""
    return max(0, min(100, (1.0 - distance) / 0.3 * 100))


@dataclass
class SearchResult:
    """A single search result."""

    id: int
    score: float
    content: str
    source_type: str  # 'chunk' or 'element'
    document_slug: str
    document_title: str
    page_number: int
    # Element-specific fields
    element_type: Optional[str] = None
    element_label: Optional[str] = None
    crop_path: Optional[str] = None
    rendered_path: Optional[str] = None  # For equations: LaTeX-rendered image
    # Chunk-specific fields
    chunk_index: Optional[int] = None


def search(
    query: str,
    limit: int = 10,
    document_slug: Optional[str] = None,
    include_chunks: bool = True,
    include_elements: bool = True,
    hybrid: bool = True,
) -> List[SearchResult]:
    """
    Hybrid search combining semantic (vector) and keyword (BM25) matching.

    Searches both chunks and elements, merging results from:
    1. Semantic search (embedding similarity)
    2. BM25 keyword search (exact term matching)
    3. Keyword-extracted query (for natural language questions)

    Args:
        query: Search query text
        limit: Maximum number of results
        document_slug: Filter to specific document (optional)
        include_chunks: Include text chunks in search
        include_elements: Include elements (figures, tables, etc.)
        hybrid: Use hybrid search (semantic + BM25). If False, semantic only.

    Returns:
        List of SearchResult objects sorted by relevance
    """
    if not check_server():
        raise RuntimeError("Embedding server not available")

    # Extract keywords for potentially better matching
    keywords = extract_keywords(query)

    # Use dict to keep best score for each result
    best_results: Dict[tuple, SearchResult] = {}

    def add_result(result: SearchResult):
        """Add result, keeping the one with best score."""
        key = (result.source_type, result.id)
        if key not in best_results or result.score < best_results[key].score:
            best_results[key] = result

    # --- Semantic search ---
    queries_to_run = [query]
    if keywords and keywords != query and len(keywords) > 2:
        queries_to_run.append(keywords)

    for q in queries_to_run:
        embedding = get_embedding(q)
        if not embedding:
            continue

        if include_chunks:
            for chunk in _search_chunks_by_vector(embedding, limit, document_slug):
                add_result(chunk)

        if include_elements:
            for elem in _search_elements_by_vector(embedding, limit, document_slug):
                add_result(elem)

    # --- BM25 keyword search ---
    if hybrid:
        # Search with original query
        if include_chunks:
            for chunk in _search_chunks_by_bm25(query, limit, document_slug):
                add_result(chunk)

        if include_elements:
            for elem in _search_elements_by_bm25(query, limit, document_slug):
                add_result(elem)

        # Also search with extracted keywords if different
        if keywords and keywords != query:
            if include_chunks:
                for chunk in _search_chunks_by_bm25(keywords, limit, document_slug):
                    add_result(chunk)

            if include_elements:
                for elem in _search_elements_by_bm25(keywords, limit, document_slug):
                    add_result(elem)

    results = list(best_results.values())

    # Sort by score (lower distance = better match)
    results.sort(key=lambda r: r.score)

    # Filter out low-relevance results
    # Two thresholds: DISTANCE_THRESHOLD (max) and MIN_CONFIDENCE_DISTANCE (quality floor)
    results = [r for r in results if r.score <= min(DISTANCE_THRESHOLD, MIN_CONFIDENCE_DISTANCE)]

    return results[:limit]


def search_chunks(
    query: str,
    limit: int = 10,
    document_slug: Optional[str] = None,
) -> List[SearchResult]:
    """Search only text chunks."""
    return search(query, limit, document_slug, include_chunks=True, include_elements=False)


def search_elements(
    query: str,
    limit: int = 10,
    document_slug: Optional[str] = None,
    element_type: Optional[str] = None,
) -> List[SearchResult]:
    """
    Search only elements (figures, tables, equations).

    Args:
        query: Search query text
        limit: Maximum number of results
        document_slug: Filter to specific document
        element_type: Filter to specific type ('figure', 'table', 'equation', etc.)
    """
    if not check_server():
        raise RuntimeError("Embedding server not available")

    embedding = get_embedding(query)
    if not embedding:
        raise RuntimeError("Failed to generate query embedding")

    return _search_elements_by_vector(embedding, limit, document_slug, element_type)


def _search_chunks_by_vector(
    embedding: List[float],
    limit: int,
    document_slug: Optional[str] = None,
) -> List[SearchResult]:
    """Search chunks using vector similarity."""
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    where_clause = ""
    params = [embedding_str, limit]

    if document_slug:
        where_clause = "AND d.slug = %s"
        params = [embedding_str, document_slug, limit]

    query = f"""
        SELECT 
            c.id,
            c.content,
            c.chunk_index,
            c.embedding <-> %s::vector AS distance,
            d.slug AS document_slug,
            d.title AS document_title,
            p.page_number
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN pages p ON c.page_id = p.id
        WHERE c.embedding IS NOT NULL
        {where_clause}
        ORDER BY c.embedding <-> %s::vector
        LIMIT %s
    """

    # Adjust params for the query (embedding appears twice)
    if document_slug:
        params = [embedding_str, document_slug, embedding_str, limit]
    else:
        params = [embedding_str, embedding_str, limit]

    rows = fetch_all(query, tuple(params))

    return [
        SearchResult(
            id=row["id"],
            score=row["distance"],
            content=row["content"],
            source_type="chunk",
            document_slug=row["document_slug"],
            document_title=row["document_title"],
            page_number=row["page_number"],
            chunk_index=row["chunk_index"],
        )
        for row in rows
    ]


def _search_elements_by_vector(
    embedding: List[float],
    limit: int,
    document_slug: Optional[str] = None,
    element_type: Optional[str] = None,
) -> List[SearchResult]:
    """Search elements using vector similarity."""
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    where_clauses = ["e.embedding IS NOT NULL"]
    params = [embedding_str]

    if document_slug:
        where_clauses.append("d.slug = %s")
        params.append(document_slug)

    if element_type:
        where_clauses.append("e.element_type = %s")
        params.append(element_type)

    where_sql = " AND ".join(where_clauses)
    params.append(embedding_str)  # For ORDER BY
    params.append(str(limit))

    query = f"""
        SELECT 
            e.id,
            e.element_type,
            e.label,
            e.description,
            e.search_text,
            e.crop_path,
            e.rendered_path,
            e.embedding <-> %s::vector AS distance,
            d.slug AS document_slug,
            d.title AS document_title,
            p.page_number
        FROM elements e
        JOIN documents d ON e.document_id = d.id
        JOIN pages p ON e.page_id = p.id
        WHERE {where_sql}
        ORDER BY e.embedding <-> %s::vector
        LIMIT %s
    """

    rows = fetch_all(query, tuple(params))

    return [
        SearchResult(
            id=row["id"],
            score=row["distance"],
            content=row["search_text"] or row["description"],
            source_type="element",
            document_slug=row["document_slug"],
            document_title=row["document_title"],
            page_number=row["page_number"],
            element_type=row["element_type"],
            element_label=row["label"],
            crop_path=row["crop_path"],
            rendered_path=row["rendered_path"],
        )
        for row in rows
    ]


def _search_chunks_by_bm25(
    query: str,
    limit: int,
    document_slug: Optional[str] = None,
) -> List[SearchResult]:
    """Search chunks using full-text search (BM25-style ranking)."""
    where_clause = ""
    if document_slug:
        where_clause = "AND d.slug = %s"

    sql = f"""
        SELECT 
            c.id,
            c.content,
            c.chunk_index,
            ts_rank(c.tsv, plainto_tsquery('english', %s)) AS bm25_score,
            d.slug AS document_slug,
            d.title AS document_title,
            p.page_number
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN pages p ON c.page_id = p.id
        WHERE c.tsv @@ plainto_tsquery('english', %s)
        {where_clause}
        ORDER BY bm25_score DESC
        LIMIT %s
    """

    if document_slug:
        params = (query, query, document_slug, limit)
    else:
        params = (query, query, limit)

    rows = fetch_all(sql, params)

    # Convert BM25 score to a "distance" for consistency (lower = better)
    # BM25 scores are typically 0-1, higher is better
    # We invert: distance = 1 - score (capped at 0)
    return [
        SearchResult(
            id=row["id"],
            score=max(0, 1.0 - row["bm25_score"] * 2),  # Scale and invert
            content=row["content"],
            source_type="chunk",
            document_slug=row["document_slug"],
            document_title=row["document_title"],
            page_number=row["page_number"],
            chunk_index=row["chunk_index"],
        )
        for row in rows
    ]


def _search_elements_by_bm25(
    query: str,
    limit: int,
    document_slug: Optional[str] = None,
    element_type: Optional[str] = None,
) -> List[SearchResult]:
    """Search elements using full-text search (BM25-style ranking)."""
    extra_clauses = []
    params: list = [query, query]  # For ts_rank and WHERE

    if document_slug:
        extra_clauses.append("d.slug = %s")
        params.append(document_slug)

    if element_type:
        extra_clauses.append("e.element_type = %s")
        params.append(element_type)

    extra_where = ""
    if extra_clauses:
        extra_where = "AND " + " AND ".join(extra_clauses)

    params.append(limit)

    sql = f"""
        SELECT 
            e.id,
            e.element_type,
            e.label,
            e.description,
            e.search_text,
            e.crop_path,
            e.rendered_path,
            ts_rank(e.tsv, plainto_tsquery('english', %s)) AS bm25_score,
            d.slug AS document_slug,
            d.title AS document_title,
            p.page_number
        FROM elements e
        JOIN documents d ON e.document_id = d.id
        JOIN pages p ON e.page_id = p.id
        WHERE e.tsv @@ plainto_tsquery('english', %s)
        {extra_where}
        ORDER BY bm25_score DESC
        LIMIT %s
    """

    rows = fetch_all(sql, tuple(params))

    return [
        SearchResult(
            id=row["id"],
            score=max(0, 1.0 - row["bm25_score"] * 2),  # Scale and invert
            content=row["search_text"] or row["description"],
            source_type="element",
            document_slug=row["document_slug"],
            document_title=row["document_title"],
            page_number=row["page_number"],
            element_type=row["element_type"],
            element_label=row["label"],
            crop_path=row["crop_path"],
            rendered_path=row["rendered_path"],
        )
        for row in rows
    ]


def get_element_by_id(element_id: int) -> Optional[Dict[str, Any]]:
    """Get full element details by ID."""
    query = """
        SELECT 
            e.*,
            d.slug AS document_slug,
            d.title AS document_title,
            p.page_number,
            p.image_path AS page_image
        FROM elements e
        JOIN documents d ON e.document_id = d.id
        JOIN pages p ON e.page_id = p.id
        WHERE e.id = %s
    """
    return fetch_one(query, (element_id,))


def get_chunk_context(chunk_id: int, context_chunks: int = 2) -> List[Dict[str, Any]]:
    """Get a chunk and its surrounding context."""
    # First get the chunk to find its page and index
    chunk = fetch_one("SELECT page_id, chunk_index FROM chunks WHERE id = %s", (chunk_id,))
    if not chunk:
        return []

    query = """
        SELECT c.id, c.content, c.chunk_index
        FROM chunks c
        WHERE c.page_id = %s
        AND c.chunk_index BETWEEN %s AND %s
        ORDER BY c.chunk_index
    """

    start_idx = max(0, chunk["chunk_index"] - context_chunks)
    end_idx = chunk["chunk_index"] + context_chunks

    return fetch_all(query, (chunk["page_id"], start_idx, end_idx))


def format_result(result: SearchResult, verbose: bool = False) -> str:
    """Format a search result for display."""
    lines = []
    score_pct = _score_from_distance(result.score)

    if result.source_type == "element":
        elem_type = result.element_type.upper() if result.element_type else "UNKNOWN"
        lines.append(f"[{elem_type}] {result.element_label}")
        lines.append(
            f"  Score: {score_pct:.1f}% | Page {result.page_number} | {result.document_title}"
        )
        if verbose:
            lines.append(f"  {result.content[:200]}...")
    else:
        lines.append(f"[TEXT] Chunk {result.chunk_index}")
        lines.append(
            f"  Score: {score_pct:.1f}% | Page {result.page_number} | {result.document_title}"
        )
        if verbose:
            lines.append(f"  {result.content[:200]}...")

    return "\n".join(lines)


# --- CLI for testing ---

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Search doclibrary")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("-n", "--limit", type=int, default=10, help="Number of results")
    parser.add_argument("-d", "--document", help="Filter by document slug")
    parser.add_argument("-t", "--type", help="Filter elements by type (figure, table, equation)")
    parser.add_argument("--chunks-only", action="store_true", help="Search only text chunks")
    parser.add_argument("--elements-only", action="store_true", help="Search only elements")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show content snippets")

    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        exit(0)

    if not check_server():
        print("ERROR: Embedding server not available")
        exit(1)

    print(f"Searching: {args.query}")
    print("=" * 60)

    try:
        if args.chunks_only:
            results = search_chunks(args.query, args.limit, args.document)
        elif args.elements_only:
            results = search_elements(args.query, args.limit, args.document, args.type)
        else:
            results = search(args.query, args.limit, args.document)

        if not results:
            print("No results found.")
        else:
            for i, result in enumerate(results, 1):
                print(f"\n{i}. {format_result(result, args.verbose)}")

    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)
