"""Integration tests for doclibrary search functionality.

These tests require:
- PostgreSQL database with pgvector extension
- Embedding server running (BGE-M3)
- Test data in the database

Run with: pytest --run-integration tests/integration/
"""

import pytest


@pytest.mark.integration
class TestSearchIntegration:
    """Integration tests for search service."""

    def test_semantic_search(self):
        """Should perform semantic search on real database."""
        from doclibrary.search import search

        results = search("map projection", limit=5)

        assert isinstance(results, list)
        # If database has data, should return results
        if results:
            assert hasattr(results[0], "content")
            assert hasattr(results[0], "score")

    def test_element_search(self):
        """Should search elements (figures, tables, etc.)."""
        from doclibrary.search import search_elements

        results = search_elements("diagram", limit=5)

        assert isinstance(results, list)
        if results:
            assert results[0].source_type == "element"

    def test_hybrid_search(self):
        """Should combine semantic and BM25 search."""
        from doclibrary.search import search

        # Use a specific term that should match via BM25
        results = search("Transverse Mercator", limit=5, hybrid=True)

        assert isinstance(results, list)

    def test_document_filter(self):
        """Should filter results by document slug."""
        from doclibrary.search import search

        results = search("projection", limit=10, document_slug="usgs_snyder")

        for result in results:
            assert result.document_slug == "usgs_snyder"


@pytest.mark.integration
class TestEmbeddingIntegration:
    """Integration tests for embedding server."""

    def test_embedding_server_health(self):
        """Should check embedding server is running."""
        from doclibrary.search.embeddings import check_server

        assert check_server() is True

    def test_generate_embedding(self):
        """Should generate embedding for text."""
        from doclibrary.search.embeddings import get_embedding
        from doclibrary.config import config

        embedding = get_embedding("test query")

        assert embedding is not None
        assert len(embedding) == config.embed_dimensions
        assert all(isinstance(x, float) for x in embedding)


@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests for database operations."""

    def test_database_connection(self):
        """Should connect to database."""
        from doclibrary.db import fetch_one

        result = fetch_one("SELECT 1 as test")

        assert result is not None
        assert result["test"] == 1

    def test_pgvector_extension(self):
        """Should have pgvector extension installed."""
        from doclibrary.db import fetch_one

        result = fetch_one(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector') as has_vector"
        )

        assert result["has_vector"] is True

    def test_documents_table(self):
        """Should have documents table."""
        from doclibrary.db import fetch_all

        results = fetch_all("SELECT COUNT(*) as count FROM documents")

        assert results is not None


@pytest.mark.integration
class TestLLMIntegration:
    """Integration tests for LLM service."""

    def test_llm_chat(self):
        """Should get response from LLM."""
        from doclibrary.core.llm import chat

        response = chat("Say hello in one word.")

        assert response is not None
        assert len(response) > 0

    def test_llm_with_context(self):
        """Should use context in LLM response."""
        from doclibrary.core.llm import chat

        context = "The capital of France is Paris."
        question = "What is the capital of France according to the context?"

        response = chat(question, context=context)

        assert "Paris" in response
