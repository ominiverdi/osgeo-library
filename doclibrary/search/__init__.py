"""Search functionality for doclibrary."""

from .embeddings import (
    check_server,
    cosine_similarity,
    get_embedding,
    get_embeddings,
    l2_normalize,
)
from .service import (
    SearchResult,
    format_result,
    get_chunk_context,
    get_element_by_id,
    search,
    search_chunks,
    search_elements,
)

__all__ = [
    # Service
    "search",
    "search_elements",
    "search_chunks",
    "SearchResult",
    "get_element_by_id",
    "get_chunk_context",
    "format_result",
    # Embeddings
    "get_embedding",
    "get_embeddings",
    "check_server",
    "l2_normalize",
    "cosine_similarity",
]
