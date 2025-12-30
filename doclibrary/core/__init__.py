"""Core utilities shared across doclibrary modules."""

from .constants import (
    SYSTEM_PROMPT,
    ANNOTATION_COLORS,
    STOPWORDS,
    ELEMENT_TYPES,
    ELEMENT_TAG_MAP,
)
from .llm import LLMClient, query_llm, check_llm_health, strip_think_tags
from .formatting import format_context_for_llm, get_source_tag, format_sources_list
from .text import (
    extract_latex_from_description,
    clean_line_numbers,
    normalize_whitespace,
    extract_keywords,
    truncate_text,
)
from .image import create_annotated_image, crop_element, render_latex_to_image

__all__ = [
    # Constants
    "SYSTEM_PROMPT",
    "ANNOTATION_COLORS",
    "STOPWORDS",
    "ELEMENT_TYPES",
    "ELEMENT_TAG_MAP",
    # LLM
    "LLMClient",
    "query_llm",
    "check_llm_health",
    "strip_think_tags",
    # Formatting
    "format_context_for_llm",
    "get_source_tag",
    "format_sources_list",
    # Text
    "extract_latex_from_description",
    "clean_line_numbers",
    "normalize_whitespace",
    "extract_keywords",
    "truncate_text",
    # Image
    "create_annotated_image",
    "crop_element",
    "render_latex_to_image",
]
