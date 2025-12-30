#!/usr/bin/env python3
"""
Text chunking for RAG ingestion.

Splits page text into overlapping chunks suitable for embedding and retrieval.
Optimized for scientific papers with paragraphs, equations, and references.

Usage:
    from doclibrary.db import chunk_text, Chunk

    # Single text
    chunks = chunk_text(page_text, chunk_size=800, overlap=200)

    # Multiple pages with metadata
    all_chunks = chunk_pages(pages_data)
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Chunk:
    """A text chunk with metadata."""

    content: str
    chunk_index: int
    start_char: int
    end_char: int
    page_number: Optional[int] = None


# Default settings (tokens approximated as chars/4)
DEFAULT_CHUNK_SIZE = 800  # ~200 tokens
DEFAULT_OVERLAP = 200  # ~50 tokens overlap


def estimate_tokens(text: str) -> int:
    """Rough token count estimate (chars / 4)."""
    return len(text) // 4


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    respect_sentences: bool = True,
) -> List[Chunk]:
    """
    Split text into overlapping chunks.

    Args:
        text: Input text to chunk
        chunk_size: Target chunk size in characters
        overlap: Overlap between consecutive chunks in characters
        respect_sentences: Try to break at sentence boundaries

    Returns:
        List of Chunk objects with content and position info
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # If text is shorter than chunk_size, return as single chunk
    if len(text) <= chunk_size:
        return [Chunk(content=text, chunk_index=0, start_char=0, end_char=len(text))]

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        # Calculate end position
        end = start + chunk_size

        if end >= len(text):
            # Last chunk - take everything remaining
            end = len(text)
        elif respect_sentences:
            # Try to find a good break point
            end = find_break_point(text, start, end, chunk_size)

        # Extract chunk content
        chunk_content = text[start:end].strip()

        if chunk_content:
            chunks.append(
                Chunk(
                    content=chunk_content,
                    chunk_index=chunk_index,
                    start_char=start,
                    end_char=end,
                )
            )
            chunk_index += 1

        # Move start position (accounting for overlap)
        if end >= len(text):
            break
        start = end - overlap

        # Ensure we make progress
        if start >= end:
            start = end

    return chunks


def find_break_point(text: str, start: int, end: int, chunk_size: int) -> int:
    """
    Find a good break point near the target end position.

    Prefers breaking at:
    1. Paragraph boundaries (double newline)
    2. Sentence boundaries (. ! ?)
    3. Clause boundaries (, ; :)
    4. Word boundaries (space)
    """
    # Search window: look back up to 20% of chunk size
    search_start = max(start, end - chunk_size // 5)
    search_text = text[search_start:end]

    # Try paragraph break first
    para_match = search_text.rfind("\n\n")
    if para_match != -1:
        return search_start + para_match + 2

    # Try sentence break
    sentence_patterns = [". ", ".\n", "! ", "!\n", "? ", "?\n"]
    best_break = -1
    for pattern in sentence_patterns:
        pos = search_text.rfind(pattern)
        if pos > best_break:
            best_break = pos

    if best_break != -1:
        return search_start + best_break + 2

    # Try clause break
    clause_patterns = [", ", "; ", ": "]
    for pattern in clause_patterns:
        pos = search_text.rfind(pattern)
        if pos != -1:
            return search_start + pos + 2

    # Fall back to word boundary
    space_pos = search_text.rfind(" ")
    if space_pos != -1:
        return search_start + space_pos + 1

    # No good break found, use original end
    return end


def chunk_pages(
    pages: List[Dict[str, Any]],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> List[Chunk]:
    """
    Chunk text from multiple pages.

    Args:
        pages: List of page dicts with 'page_number' and 'text' keys
        chunk_size: Target chunk size in characters
        overlap: Overlap between chunks

    Returns:
        List of Chunk objects with page_number set
    """
    all_chunks = []
    global_index = 0

    for page in pages:
        page_num = page.get("page_number", 0)
        text = page.get("text", "")

        if not text:
            continue

        page_chunks = chunk_text(text, chunk_size, overlap)

        for chunk in page_chunks:
            chunk.page_number = page_num
            chunk.chunk_index = global_index
            all_chunks.append(chunk)
            global_index += 1

    return all_chunks


def clean_text_for_chunking(text: str) -> str:
    """
    Clean text before chunking.

    - Normalize whitespace
    - Remove excessive newlines
    - Keep paragraph structure
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse multiple spaces (but not newlines)
    text = re.sub(r"[ \t]+", " ", text)

    # Collapse more than 2 consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip leading/trailing whitespace from lines
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


# --- CLI for testing ---

if __name__ == "__main__":
    # Test with sample text
    sample_text = """
    This is the first paragraph of a scientific paper. It contains an introduction
    to the topic and sets up the problem that will be addressed. The methodology
    is described in detail.
    
    This is the second paragraph. It goes into more technical details about the
    approach used in the study. Various equations and formulas may be referenced,
    such as E = mc^2 for energy-mass equivalence.
    
    The third paragraph discusses results. Statistical analysis shows significant
    improvements over baseline methods. Table 1 presents the key findings.
    
    Finally, the conclusion summarizes the main contributions and suggests
    directions for future work. The implications for the field are discussed.
    """

    print("Testing text chunking...")
    print(f"Input length: {len(sample_text)} chars (~{estimate_tokens(sample_text)} tokens)")
    print()

    chunks = chunk_text(sample_text, chunk_size=300, overlap=50)

    print(f"Generated {len(chunks)} chunks:")
    print("-" * 60)
    for chunk in chunks:
        print(
            f"Chunk {chunk.chunk_index}: chars {chunk.start_char}-{chunk.end_char} "
            f"(len={len(chunk.content)})"
        )
        print(f'  "{chunk.content[:80]}..."')
        print()
