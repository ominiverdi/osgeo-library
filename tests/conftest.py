"""Pytest configuration and fixtures for doclibrary tests."""

import os
import pytest
from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import MagicMock


# --- Test database configuration ---

TEST_DB_NAME = "doclibrary_test"


@pytest.fixture
def mock_config(monkeypatch):
    """Mock configuration for unit tests."""
    monkeypatch.setenv("DOCLIBRARY_DB_NAME", TEST_DB_NAME)
    monkeypatch.setenv("DOCLIBRARY_LLM_URL", "http://localhost:8080/v1/chat/completions")
    monkeypatch.setenv("DOCLIBRARY_EMBED_URL", "http://localhost:8094/embedding")


@pytest.fixture
def mock_db_connection():
    """Mock database connection for unit tests."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return mock_conn


# --- Sample data fixtures ---


@dataclass
class MockSearchResult:
    """Mock SearchResult for testing formatting functions."""

    id: int
    score: float
    content: str
    source_type: str
    document_slug: str
    document_title: str
    page_number: int
    element_type: Optional[str] = None
    element_label: Optional[str] = None
    crop_path: Optional[str] = None
    rendered_path: Optional[str] = None
    chunk_index: Optional[int] = None


@pytest.fixture
def sample_chunk_result():
    """Sample text chunk search result."""
    return MockSearchResult(
        id=1,
        score=0.85,
        content="The Transverse Mercator projection is a conformal map projection.",
        source_type="chunk",
        document_slug="usgs_snyder",
        document_title="Map Projections: A Working Manual",
        page_number=42,
        chunk_index=3,
    )


@pytest.fixture
def sample_figure_result():
    """Sample figure element search result."""
    return MockSearchResult(
        id=10,
        score=0.75,
        content="Figure showing the Transverse Mercator cylinder tangent to the central meridian.",
        source_type="element",
        document_slug="usgs_snyder",
        document_title="Map Projections: A Working Manual",
        page_number=44,
        element_type="figure",
        element_label="Figure 8-1",
        crop_path="/data/usgs_snyder/elements/fig_8_1.png",
    )


@pytest.fixture
def sample_equation_result():
    """Sample equation element search result."""
    return MockSearchResult(
        id=20,
        score=0.80,
        content="x = k_0 * N * (A + (1 - T + C) * A^3 / 6)",
        source_type="element",
        document_slug="usgs_snyder",
        document_title="Map Projections: A Working Manual",
        page_number=45,
        element_type="equation",
        element_label="Equation 8-9",
        crop_path="/data/usgs_snyder/elements/eq_8_9.png",
        rendered_path="/data/usgs_snyder/elements/eq_8_9_rendered.png",
    )


@pytest.fixture
def sample_table_result():
    """Sample table element search result."""
    return MockSearchResult(
        id=30,
        score=0.70,
        content="Table of standard parallels for UTM zones",
        source_type="element",
        document_slug="usgs_snyder",
        document_title="Map Projections: A Working Manual",
        page_number=50,
        element_type="table",
        element_label="Table 8-2",
        crop_path="/data/usgs_snyder/elements/tab_8_2.png",
    )


@pytest.fixture
def sample_results_list(sample_chunk_result, sample_figure_result, sample_equation_result):
    """List of mixed search results."""
    return [sample_chunk_result, sample_figure_result, sample_equation_result]


# --- Text processing fixtures ---


@pytest.fixture
def text_with_line_numbers():
    """Sample text with ICLR-style line numbers."""
    return """000 Abstract
001 This paper presents a novel approach
002 to map projection distortion analysis.
003 We propose a method that combines
004 traditional geodetic calculations with
005 modern machine learning techniques.
006 
007 1 Introduction
008 Map projections have been studied
009 extensively for centuries, but
010 distortion minimization remains
011 a challenging problem in cartography."""


@pytest.fixture
def text_without_line_numbers():
    """Expected output after line number removal."""
    return """Abstract
This paper presents a novel approach
to map projection distortion analysis.
We propose a method that combines
traditional geodetic calculations with
modern machine learning techniques.

1 Introduction
Map projections have been studied
extensively for centuries, but
distortion minimization remains
a challenging problem in cartography."""


@pytest.fixture
def latex_description():
    """Sample description containing LaTeX."""
    return "The equation for computing x: LaTeX: x = k_0 \\cdot N \\cdot A"


# --- Integration test markers ---


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests requiring external services (postgres, llm, embedding)"
    )
    config.addinivalue_line("markers", "slow: marks tests as slow running")


# --- Skip integration tests by default ---


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --run-integration is passed."""
    if config.getoption("--run-integration", default=False):
        return

    skip_integration = pytest.mark.skip(reason="Need --run-integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests (requires postgres, llm, embedding server)",
    )
