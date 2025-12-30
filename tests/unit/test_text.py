"""Unit tests for doclibrary.core.text module."""

import pytest
from doclibrary.core.text import (
    extract_latex_from_description,
    clean_line_numbers,
    normalize_whitespace,
    extract_keywords,
    truncate_text,
)


class TestExtractLatexFromDescription:
    """Tests for extract_latex_from_description function."""

    def test_extracts_latex_with_prefix(self):
        """Should extract LaTeX after 'LaTeX:' prefix."""
        description = "The equation for x: LaTeX: x = k_0 \\cdot N"
        result = extract_latex_from_description(description)
        assert result == "x = k_0 \\cdot N"

    def test_case_insensitive(self):
        """Should handle different cases of 'LaTeX' prefix."""
        assert extract_latex_from_description("latex: y = mx + b") == "y = mx + b"
        assert extract_latex_from_description("LATEX: y = mx + b") == "y = mx + b"
        assert extract_latex_from_description("LaTeX: y = mx + b") == "y = mx + b"

    def test_returns_none_for_no_latex(self):
        """Should return None when no LaTeX prefix found."""
        assert extract_latex_from_description("Just a regular description") is None
        assert extract_latex_from_description("Contains latex word but no colon") is None

    def test_returns_none_for_empty_input(self):
        """Should return None for empty or None input."""
        assert extract_latex_from_description("") is None
        assert extract_latex_from_description(None) is None

    def test_stops_at_new_sentence(self):
        """Should stop extraction at sentence boundary."""
        description = "LaTeX: x = y^2. This is a description."
        result = extract_latex_from_description(description)
        assert result == "x = y^2"

    def test_preserves_complex_latex(self):
        """Should preserve complex LaTeX expressions."""
        description = "LaTeX: \\frac{d}{dx}\\int_a^x f(t)dt = f(x)"
        result = extract_latex_from_description(description)
        assert result == "\\frac{d}{dx}\\int_a^x f(t)dt = f(x)"


class TestCleanLineNumbers:
    """Tests for clean_line_numbers function."""

    def test_removes_three_digit_line_numbers(self):
        """Should remove 3-digit line numbers from text."""
        # Create text with consistent 3-digit line numbers (more than 10 lines)
        lines = [f"{i:03d} Line {i} content" for i in range(15)]
        text = "\n".join(lines)

        result = clean_line_numbers(text)

        # Line numbers should be removed
        assert "000" not in result
        assert "Line 0 content" in result
        assert "Line 14 content" in result

    def test_preserves_text_without_line_numbers(self):
        """Should not modify text without line numbers."""
        text = "This is normal text\nWith multiple lines\nBut no line numbers"
        result = clean_line_numbers(text)
        assert result == text

    def test_handles_empty_input(self):
        """Should handle empty or None input."""
        assert clean_line_numbers("") == ""
        assert clean_line_numbers(None) is None

    def test_requires_majority_numbered_lines(self):
        """Should only remove numbers if >50% of first 20 lines have them."""
        # Only 2 numbered lines - should not trigger removal
        text = "000 First line\n001 Second line\nRegular line\nAnother line"
        result = clean_line_numbers(text)
        assert result == text  # Unchanged


class TestNormalizeWhitespace:
    """Tests for normalize_whitespace function."""

    def test_collapses_multiple_spaces(self):
        """Should collapse multiple spaces to single space."""
        text = "word1    word2     word3"
        result = normalize_whitespace(text)
        assert result == "word1 word2 word3"

    def test_normalizes_multiple_newlines(self):
        """Should normalize 3+ newlines to double newline."""
        text = "Para 1\n\n\n\nPara 2"
        result = normalize_whitespace(text)
        assert result == "Para 1\n\nPara 2"

    def test_strips_line_whitespace(self):
        """Should strip whitespace from each line."""
        text = "  line 1  \n  line 2  "
        result = normalize_whitespace(text)
        assert result == "line 1\nline 2"

    def test_handles_empty_input(self):
        """Should handle empty or None input."""
        assert normalize_whitespace("") == ""
        assert normalize_whitespace(None) is None

    def test_preserves_single_newlines(self):
        """Should preserve single newlines (not paragraph breaks)."""
        text = "line 1\nline 2\nline 3"
        result = normalize_whitespace(text)
        assert result == "line 1\nline 2\nline 3"


class TestExtractKeywords:
    """Tests for extract_keywords function."""

    def test_removes_stopwords(self):
        """Should remove common stopwords."""
        query = "what is the transverse mercator projection"
        result = extract_keywords(query)
        assert "what" not in result.lower()
        assert "is" not in result.lower()
        assert "the" not in result.lower()
        assert "transverse" in result
        assert "mercator" in result
        assert "projection" in result

    def test_preserves_capitalized_words(self):
        """Should preserve capitalized words (proper nouns)."""
        query = "who is Adam Stewart"
        result = extract_keywords(query)
        assert "Adam" in result
        assert "Stewart" in result

    def test_returns_space_separated(self):
        """Should return keywords as space-separated string."""
        query = "show me the oblique projection"
        result = extract_keywords(query)
        assert isinstance(result, str)
        words = result.split()
        assert "oblique" in words
        assert "projection" in words

    def test_handles_query_with_all_stopwords(self):
        """Should handle queries with mostly stopwords."""
        query = "what is the"
        result = extract_keywords(query)
        # All stopwords, but should not crash
        assert isinstance(result, str)


class TestTruncateText:
    """Tests for truncate_text function."""

    def test_truncates_long_text(self):
        """Should truncate text longer than max_length."""
        text = "word " * 200  # 1000 characters
        result = truncate_text(text, max_length=50)
        assert len(result) <= 50
        assert result.endswith("...")

    def test_preserves_short_text(self):
        """Should not modify text shorter than max_length."""
        text = "Short text"
        result = truncate_text(text, max_length=500)
        assert result == text

    def test_truncates_at_word_boundary(self):
        """Should truncate at word boundary, not mid-word."""
        text = "one two three four five six seven"
        result = truncate_text(text, max_length=20)
        # Should not end with partial word
        assert not result.rstrip(".").endswith("thre")

    def test_custom_suffix(self):
        """Should use custom suffix when specified."""
        text = "A very long text " * 10
        result = truncate_text(text, max_length=30, suffix=" [...]")
        assert result.endswith(" [...]")

    def test_handles_empty_input(self):
        """Should handle empty or None input."""
        assert truncate_text("", max_length=100) == ""
        assert truncate_text(None, max_length=100) is None
