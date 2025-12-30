"""
doclibrary - Extract and search visual elements from scientific PDFs.

This library provides tools to:
- Extract figures, tables, diagrams, and equations from PDFs using vision models
- Store extracted content with semantic embeddings in PostgreSQL
- Search documents using natural language queries
- Chat with an LLM that has access to the document knowledge base

Usage:
    from doclibrary.config import config
    from doclibrary.search import search
    from doclibrary.extraction import extract_document

CLI:
    doclibrary extract paper.pdf --pages 1-10
    doclibrary search "map projection equations"
    doclibrary chat
    doclibrary serve
"""

__version__ = "1.0.0"
__author__ = "Lorenzo Becchi"
