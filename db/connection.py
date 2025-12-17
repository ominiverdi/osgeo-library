#!/usr/bin/env python3
"""
Database connection and helper functions for osgeo_library.

PostgreSQL connection uses peer authentication (current Unix user).
No password needed when running as the database owner.

Usage:
    from db.connection import get_connection, execute, fetch_one, fetch_all

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

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Any, List, Optional, Dict

# Database configuration
DB_NAME = os.environ.get("OSGEO_DB_NAME", "osgeo_library")
DB_HOST = os.environ.get("OSGEO_DB_HOST", "")  # Empty = Unix socket (peer auth)
DB_PORT = os.environ.get("OSGEO_DB_PORT", "5432")
DB_USER = os.environ.get("OSGEO_DB_USER", "")  # Empty = current Unix user
DB_PASSWORD = os.environ.get("OSGEO_DB_PASSWORD", "")


def get_connection_string() -> str:
    """Build connection string from environment."""
    parts = [f"dbname={DB_NAME}"]
    if DB_HOST:
        parts.append(f"host={DB_HOST}")
    if DB_PORT:
        parts.append(f"port={DB_PORT}")
    if DB_USER:
        parts.append(f"user={DB_USER}")
    if DB_PASSWORD:
        parts.append(f"password={DB_PASSWORD}")
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


def execute(query: str, params: tuple | None = None) -> None:
    """Execute a query without returning results."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()


def fetch_one(query: str, params: tuple | None = None) -> Optional[Dict[str, Any]]:
    """Execute query and return first row as dict, or None."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_all(query: str, params: tuple | None = None) -> List[Dict[str, Any]]:
    """Execute query and return all rows as list of dicts."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def insert_returning(query: str, params: tuple | None = None) -> Any:
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
    metadata: dict | None = None,
) -> int:
    """Insert a document and return its ID."""
    import json

    query = """
        INSERT INTO documents (slug, title, source_file, extraction_date, model, metadata)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    return insert_returning(
        query,
        (slug, title, source_file, extraction_date, model, json.dumps(metadata or {})),
    )


def get_document_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get document by slug."""
    return fetch_one("SELECT * FROM documents WHERE slug = %s", (slug,))


def delete_document(doc_id: int) -> None:
    """Delete document and all related data (cascades)."""
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
) -> int:
    """Insert a page and return its ID."""
    query = """
        INSERT INTO pages (document_id, page_number, image_path, annotated_image_path,
                          full_text, width, height)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
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
    embedding: List[float] | None = None,
) -> int:
    """Insert a text chunk and return its ID."""
    import json

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
    search_text: str,
    latex: str,
    crop_path: str,
    rendered_path: str,
    bbox_pixels: List[int] | None,
    embedding: List[float] | None = None,
) -> int:
    """Insert an element and return its ID."""
    import json

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
            label,
            description,
            search_text,
            latex,
            crop_path,
            rendered_path,
            bbox_pixels,
            emb_str,
        ),
    )


# --- Search operations ---


def search_chunks_by_embedding(
    embedding: List[float], limit: int = 5, document_id: int | None = None
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
    document_id: int | None = None,
    element_type: str | None = None,
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

    # Test connection
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
