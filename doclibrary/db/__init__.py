"""Database operations for doclibrary."""

from .chunking import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    Chunk,
    chunk_pages,
    chunk_text,
    clean_text_for_chunking,
)
from .connection import (
    delete_document,
    execute,
    fetch_all,
    fetch_one,
    get_connection,
    get_connection_string,
    get_document_by_slug,
    insert_chunk,
    insert_document,
    insert_element,
    insert_page,
    insert_returning,
    search_chunks_by_embedding,
    search_elements_by_embedding,
)
from .ingest import (
    ingest_all,
    ingest_document,
    list_available_documents,
)

__all__ = [
    # Connection
    "get_connection",
    "get_connection_string",
    "fetch_all",
    "fetch_one",
    "execute",
    "insert_returning",
    # Document operations
    "get_document_by_slug",
    "delete_document",
    "insert_document",
    "insert_page",
    "insert_chunk",
    "insert_element",
    # Search operations
    "search_chunks_by_embedding",
    "search_elements_by_embedding",
    # Chunking
    "chunk_text",
    "chunk_pages",
    "clean_text_for_chunking",
    "Chunk",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_OVERLAP",
    # Ingestion
    "ingest_document",
    "ingest_all",
    "list_available_documents",
]
