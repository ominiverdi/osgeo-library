"""Unit tests for doclibrary.core.formatting module."""

import pytest
from doclibrary.core.formatting import (
    get_source_tag,
    format_context_for_llm,
    format_sources_list,
)


class TestGetSourceTag:
    """Tests for get_source_tag function."""

    def test_chunk_tag(self, sample_chunk_result):
        """Should return [t:N] for text chunks."""
        tag = get_source_tag(sample_chunk_result, 0)
        assert tag == "[t:1]"

    def test_figure_tag(self, sample_figure_result):
        """Should return [fig:N] for figures."""
        tag = get_source_tag(sample_figure_result, 0)
        assert tag == "[fig:1]"

    def test_equation_tag(self, sample_equation_result):
        """Should return [eq:N] for equations."""
        tag = get_source_tag(sample_equation_result, 1)
        assert tag == "[eq:2]"

    def test_table_tag(self, sample_table_result):
        """Should return [tab:N] for tables."""
        tag = get_source_tag(sample_table_result, 2)
        assert tag == "[tab:3]"

    def test_one_based_indexing(self, sample_chunk_result):
        """Should use 1-based indexing for display."""
        assert get_source_tag(sample_chunk_result, 0) == "[t:1]"
        assert get_source_tag(sample_chunk_result, 4) == "[t:5]"

    def test_handles_dict_result(self):
        """Should handle dict-style results."""
        result_dict = {
            "source_type": "element",
            "element_type": "figure",
        }
        tag = get_source_tag(result_dict, 0)
        assert tag == "[fig:1]"

    def test_defaults_to_text_tag(self):
        """Should default to [t:N] for unknown types."""
        result_dict = {"source_type": "unknown"}
        tag = get_source_tag(result_dict, 0)
        assert tag == "[t:1]"


class TestFormatContextForLlm:
    """Tests for format_context_for_llm function."""

    def test_formats_mixed_results(self, sample_results_list):
        """Should format list of mixed results."""
        context = format_context_for_llm(sample_results_list)

        assert "[t:1]" in context
        assert "[fig:2]" in context
        assert "[eq:3]" in context
        assert "Map Projections" in context

    def test_includes_element_info(self, sample_figure_result):
        """Should include element type and label."""
        context = format_context_for_llm([sample_figure_result])

        assert "FIGURE" in context
        assert "Figure 8-1" in context

    def test_includes_page_info(self, sample_chunk_result):
        """Should include document and page info."""
        context = format_context_for_llm([sample_chunk_result])

        assert "page 42" in context
        assert "Map Projections: A Working Manual" in context

    def test_empty_list(self):
        """Should return empty string for empty list."""
        assert format_context_for_llm([]) == ""

    def test_truncates_content(self, sample_chunk_result):
        """Should truncate long content."""
        # Make content very long
        sample_chunk_result.content = "x " * 500  # 1000 chars
        context = format_context_for_llm([sample_chunk_result])

        # Content should be limited
        assert len(context) < 600


class TestFormatSourcesList:
    """Tests for format_sources_list function."""

    def test_formats_list(self, sample_results_list):
        """Should format results as numbered list."""
        sources = format_sources_list(sample_results_list)

        lines = sources.split("\n")
        assert len(lines) == 3
        assert "[t:1]" in lines[0]
        assert "[fig:2]" in lines[1]
        assert "[eq:3]" in lines[2]

    def test_includes_document_info(self, sample_figure_result):
        """Should include document and page info."""
        sources = format_sources_list([sample_figure_result])

        assert "Map Projections" in sources
        assert "p.44" in sources

    def test_includes_score_with_fn(self, sample_chunk_result):
        """Should include score when score_fn provided."""

        def score_to_pct(distance):
            return (1.0 - distance) * 100

        sources = format_sources_list([sample_chunk_result], score_fn=score_to_pct)

        assert "%" in sources

    def test_empty_list(self):
        """Should return message for empty list."""
        sources = format_sources_list([])
        assert "No sources" in sources

    def test_element_formatting(self, sample_table_result):
        """Should format element with type and label."""
        sources = format_sources_list([sample_table_result])

        assert "TABLE" in sources
        assert "Table 8-2" in sources
