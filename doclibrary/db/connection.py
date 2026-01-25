#!/usr/bin/env python3
"""
Database connection and helper functions for doclibrary.

PostgreSQL connection uses peer authentication (current Unix user).
No password needed when running as the database owner.

Usage:
    from doclibrary.db import get_connection, execute, fetch_one, fetch_all

    # Simple query
    rows = fetch_all("SELECT * FROM documents")

    # With parameters
    doc = fetch_one("SELECT * FROM documents WHERE slug = %s", (slug,))

    # Insert and get ID
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO documents (slug, title) VALUES (%s, %s) RETURNING id",
                       (slug, title))
            doc_id = cur.fetchone()[0]
        conn.commit()
"""

import json
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union

import psycopg2
from psycopg2.extras import RealDictCursor

from doclibrary.config import config


def get_connection_string() -> str:
    """Build connection string from config."""
    parts = [f"dbname={config.db_name}"]
    if config.db_host:
        parts.append(f"host={config.db_host}")
    if config.db_port:
        parts.append(f"port={config.db_port}")
    if config.db_user:
        parts.append(f"user={config.db_user}")
    if config.db_password:
        parts.append(f"password={config.db_password}")
    return " ".join(parts)


@contextmanager
def get_connection():
    """
    Get a database connection using context manager.

    Usage:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.commit()
    """
    conn = None
    try:
        conn = psycopg2.connect(get_connection_string())
        yield conn
    finally:
        if conn:
            conn.close()


def execute(query: str, params: Optional[tuple] = None) -> None:
    """Execute a query without returning results."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()


def fetch_one(query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
    """Execute query and return first row as dict, or None."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_all(query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
    """Execute query and return all rows as list of dicts."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def insert_returning(query: str, params: Optional[tuple] = None) -> Any:
    """Execute INSERT ... RETURNING and return the value."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            result = row[0] if row else None
        conn.commit()
        return result


# --- Document operations ---


def insert_document(
    slug: str,
    title: str,
    source_file: str,
    extraction_date: str,
    model: str,
    metadata: Optional[dict] = None,
    summary: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    license: Optional[str] = None,
) -> int:
    """Insert a document and return its ID."""
    query = """
        INSERT INTO documents (slug, title, source_file, extraction_date, model, metadata,
                              summary, keywords, license)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    return insert_returning(
        query,
        (
            slug,
            title,
            source_file,
            extraction_date,
            model,
            json.dumps(metadata or {}),
            summary,
            keywords,
            license,
        ),
    )


def get_document_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get document by slug."""
    return fetch_one("SELECT * FROM documents WHERE slug = %s", (slug,))


def delete_document(doc_id: Union[int, str]) -> None:
    """Delete document and all related data (cascades).

    Args:
        doc_id: Document ID (int) or slug (str)
    """
    if isinstance(doc_id, str):
        # It's a slug, get the ID first
        doc = get_document_by_slug(doc_id)
        if doc:
            doc_id = doc["id"]
        else:
            return  # Document not found
    execute("DELETE FROM documents WHERE id = %s", (doc_id,))


# --- Page operations ---


def insert_page(
    document_id: int,
    page_number: int,
    image_path: str,
    annotated_image_path: str,
    full_text: str,
    width: int,
    height: int,
    summary: Optional[str] = None,
    keywords: Optional[List[str]] = None,
) -> int:
    """Insert a page and return its ID."""
    query = """
        INSERT INTO pages (document_id, page_number, image_path, annotated_image_path,
                          full_text, width, height, summary, keywords)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    return insert_returning(
        query,
        (
            document_id,
            page_number,
            image_path,
            annotated_image_path,
            full_text,
            width,
            height,
            summary,
            keywords,
        ),
    )


# --- Chunk operations ---


def insert_chunk(
    document_id: int,
    page_id: int,
    content: str,
    chunk_index: int,
    start_char: int,
    end_char: int,
    embedding: Optional[List[float]] = None,
) -> int:
    """Insert a text chunk and return its ID."""
    query = """
        INSERT INTO chunks (document_id, page_id, content, chunk_index, 
                           start_char, end_char, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    # Convert embedding list to pgvector format
    emb_str = None
    if embedding:
        emb_str = "[" + ",".join(str(x) for x in embedding) + "]"

    return insert_returning(
        query,
        (document_id, page_id, content, chunk_index, start_char, end_char, emb_str),
    )


# --- Element operations ---


def insert_element(
    document_id: int,
    page_id: int,
    element_type: str,
    label: str,
    description: str,
    search_text: Optional[str],
    latex: Optional[str],
    crop_path: str,
    rendered_path: Optional[str],
    bbox_pixels: Optional[List[int]],
    embedding: Optional[List[float]] = None,
) -> int:
    """Insert an element and return its ID."""
    query = """
        INSERT INTO elements (document_id, page_id, element_type, label, description,
                             search_text, latex, crop_path, rendered_path, bbox_pixels, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    # Convert embedding list to pgvector format
    emb_str = None
    if embedding:
        emb_str = "[" + ",".join(str(x) for x in embedding) + "]"

    return insert_returning(
        query,
        (
            document_id,
            page_id,
            element_type,
            label[:100] if label else "",
            description,
            search_text or "",
            latex or "",
            crop_path,
            rendered_path or "",
            bbox_pixels,
            emb_str,
        ),
    )


# --- Search operations ---


def search_chunks_by_embedding(
    embedding: List[float],
    limit: int = 5,
    document_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Search chunks by embedding similarity."""
    emb_str = "[" + ",".join(str(x) for x in embedding) + "]"

    if document_id:
        query = """
            SELECT c.*, d.slug as document_slug,
                   1 - (c.embedding <=> %s::vector) as similarity
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.document_id = %s AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """
        return fetch_all(query, (emb_str, document_id, emb_str, limit))
    else:
        query = """
            SELECT c.*, d.slug as document_slug,
                   1 - (c.embedding <=> %s::vector) as similarity
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """
        return fetch_all(query, (emb_str, emb_str, limit))


def search_elements_by_embedding(
    embedding: List[float],
    limit: int = 3,
    document_id: Optional[int] = None,
    element_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search elements by embedding similarity."""
    emb_str = "[" + ",".join(str(x) for x in embedding) + "]"

    conditions = ["e.embedding IS NOT NULL"]
    params: list = [emb_str]

    if document_id:
        conditions.append("e.document_id = %s")
        params.append(document_id)
    if element_type:
        conditions.append("e.element_type = %s")
        params.append(element_type)

    params.extend([emb_str, limit])

    query = f"""
        SELECT e.*, d.slug as document_slug, p.page_number,
               1 - (e.embedding <=> %s::vector) as similarity
        FROM elements e
        JOIN documents d ON e.document_id = d.id
        JOIN pages p ON e.page_id = p.id
        WHERE {" AND ".join(conditions)}
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
    """
    return fetch_all(query, tuple(params))


# --- CLI for testing ---

if __name__ == "__main__":
    print("Testing database connection...")
    print(f"Connection string: {get_connection_string()}")

    try:
        result = fetch_one("SELECT version()")
        if result:
            print(f"PostgreSQL version: {result['version'][:50]}...")

        # Test tables
        tables = fetch_all("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        print(f"Tables: {[t['table_name'] for t in tables]}")

        # Test pgvector
        result = fetch_one("SELECT '[1,2,3]'::vector")
        print(f"pgvector working: {result is not None}")

        print("\nConnection test passed!")

    except Exception as e:
        print(f"ERROR: {e}")
