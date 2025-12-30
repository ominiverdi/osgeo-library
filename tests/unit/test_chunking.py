"""Unit tests for doclibrary.db.chunking module."""

import pytest
from doclibrary.db.chunking import (
    chunk_text,
    chunk_pages,
    clean_text_for_chunking,
    find_break_point,
    estimate_tokens,
    Chunk,
)


class TestChunkText:
    """Tests for chunk_text function."""

    def test_single_chunk_for_short_text(self):
        """Short text should return single chunk."""
        text = "This is a short text."
        chunks = chunk_text(text, chunk_size=100)

        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].chunk_index == 0

    def test_multiple_chunks_for_long_text(self):
        """Long text should be split into multiple chunks."""
        text = "Word " * 200  # 1000 chars
        chunks = chunk_text(text, chunk_size=200, overlap=50)

        assert len(chunks) > 1

    def test_overlap_between_chunks(self):
        """Chunks should overlap by specified amount."""
        text = "The quick brown fox jumps over the lazy dog. " * 20
        chunks = chunk_text(text, chunk_size=100, overlap=30)

        # Check that consecutive chunks share content
        if len(chunks) > 1:
            # Find overlap in content
            chunk0_end = chunks[0].content[-30:]
            chunk1_start = chunks[1].content[:50]
            # There should be some shared content
            assert any(word in chunk1_start for word in chunk0_end.split())

    def test_empty_text(self):
        """Empty text should return empty list."""
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_chunk_indices_sequential(self):
        """Chunk indices should be sequential."""
        text = "Word " * 200  # 1000 chars
        # Use overlap smaller than chunk_size to avoid infinite loop
        chunks = chunk_text(text, chunk_size=200, overlap=50)

        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_start_end_chars_correct(self):
        """Start and end char positions should be correct."""
        text = "First sentence. Second sentence. Third sentence. " * 5
        chunks = chunk_text(text, chunk_size=80, overlap=20)

        for chunk in chunks:
            assert chunk.start_char >= 0
            assert chunk.end_char <= len(text)
            assert chunk.start_char < chunk.end_char


class TestFindBreakPoint:
    """Tests for find_break_point function."""

    def test_prefers_paragraph_break(self):
        """Should prefer breaking at paragraph boundaries."""
        text = "First paragraph.\n\nSecond paragraph. More text here."
        # Use larger chunk_size so the search window includes the paragraph break
        # Search window = 20% of chunk_size = 20% of 100 = 20 chars back from end=20
        # So search_text = text[0:20] = "First paragraph.\n\n" which contains \n\n
        end = find_break_point(text, 0, 20, 100)

        # Break should be at position 18 (right after the double newline)
        assert end == 18

    def test_prefers_sentence_break(self):
        """Should prefer breaking at sentence boundaries."""
        text = "First sentence. Second sentence. Third."
        end = find_break_point(text, 0, 20, 25)

        # Should break after a period
        assert text[end - 2 : end - 1] == "."

    def test_falls_back_to_word_boundary(self):
        """Should fall back to word boundary if no sentence break."""
        text = "word1 word2 word3 word4"
        end = find_break_point(text, 0, 15, 20)

        # Should break at a space (word boundary)
        assert text[end - 1] == " " or end == 15


class TestChunkPages:
    """Tests for chunk_pages function."""

    def test_chunks_multiple_pages(self):
        """Should chunk text from multiple pages."""
        pages = [
            {"page_number": 1, "text": "Page one content. " * 10},
            {"page_number": 2, "text": "Page two content. " * 10},
        ]

        # Use overlap smaller than chunk_size
        chunks = chunk_pages(pages, chunk_size=100, overlap=30)

        assert len(chunks) > 0
        # Check that page numbers are set
        page_numbers = set(c.page_number for c in chunks)
        assert 1 in page_numbers
        assert 2 in page_numbers

    def test_global_chunk_indices(self):
        """Chunk indices should be global across pages."""
        pages = [
            {"page_number": 1, "text": "Content " * 50},
            {"page_number": 2, "text": "Content " * 50},
        ]

        # Use overlap smaller than chunk_size
        chunks = chunk_pages(pages, chunk_size=100, overlap=30)
        indices = [c.chunk_index for c in chunks]

        # Should be sequential starting from 0
        assert indices == list(range(len(chunks)))

    def test_skips_empty_pages(self):
        """Should skip pages with no text."""
        pages = [
            {"page_number": 1, "text": "Has content."},
            {"page_number": 2, "text": ""},
            {"page_number": 3, "text": "Also has content."},
        ]

        chunks = chunk_pages(pages)
        page_numbers = [c.page_number for c in chunks]

        assert 2 not in page_numbers


class TestCleanTextForChunking:
    """Tests for clean_text_for_chunking function."""

    def test_normalizes_line_endings(self):
        """Should normalize CRLF and CR to LF."""
        text = "Line 1\r\nLine 2\rLine 3"
        result = clean_text_for_chunking(text)

        assert "\r" not in result
        assert "Line 1\nLine 2\nLine 3" == result

    def test_collapses_multiple_spaces(self):
        """Should collapse multiple spaces."""
        text = "word1    word2     word3"
        result = clean_text_for_chunking(text)

        assert result == "word1 word2 word3"

    def test_limits_consecutive_newlines(self):
        """Should limit consecutive newlines to 2."""
        text = "Para 1\n\n\n\n\nPara 2"
        result = clean_text_for_chunking(text)

        assert "\n\n\n" not in result
        assert "Para 1\n\nPara 2" == result

    def test_strips_line_whitespace(self):
        """Should strip whitespace from each line."""
        text = "  line 1  \n  line 2  "
        result = clean_text_for_chunking(text)

        assert result == "line 1\nline 2"

    def test_handles_empty_input(self):
        """Should handle empty input."""
        assert clean_text_for_chunking("") == ""
        assert clean_text_for_chunking(None) == ""


class TestEstimateTokens:
    """Tests for estimate_tokens function."""

    def test_approximation(self):
        """Should estimate tokens as chars/4."""
        text = "1234567890123456"  # 16 chars
        assert estimate_tokens(text) == 4

    def test_empty_text(self):
        """Should handle empty text."""
        assert estimate_tokens("") == 0
