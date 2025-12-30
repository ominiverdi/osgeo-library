"""Context and source formatting utilities for doclibrary."""

from typing import Any, Callable, Dict, List, Optional

from .constants import ELEMENT_TAG_MAP


def get_source_tag(result: Any, index: int) -> str:
    """Get citation tag for a search result.

    Args:
        result: SearchResult object with source_type and element_type attributes
        index: Zero-based index in results list

    Returns:
        Simple citation tag like "[1]", "[2]", "[3]"
    """
    # Convert to 1-based index for display
    num = index + 1
    return f"[{num}]"


def format_context_for_llm(results: List[Any]) -> str:
    """Format search results as context for LLM.

    Args:
        results: List of SearchResult objects or dicts

    Returns:
        Formatted context string with citation tags
    """
    if not results:
        return ""

    parts = []
    for i, r in enumerate(results):
        tag = get_source_tag(r, i)

        # Handle both dataclass and dict results
        if hasattr(r, "source_type"):
            source_type = r.source_type
            element_type = getattr(r, "element_type", None)
            element_label = getattr(r, "element_label", "")
            document_title = getattr(r, "document_title", "Unknown")
            page_number = getattr(r, "page_number", "?")
            content = getattr(r, "content", "")
        else:
            source_type = r.get("source_type", "chunk")
            element_type = r.get("element_type")
            element_label = r.get("element_label", "")
            document_title = r.get("document_title", "Unknown")
            page_number = r.get("page_number", "?")
            content = r.get("content", "")

        # Truncate content
        content_preview = content[:500] if content else ""

        if source_type == "element" and element_type:
            parts.append(
                f"{tag} {element_type.upper()}: {element_label} "
                f"(from {document_title}, page {page_number})\n"
                f"    {content_preview}"
            )
        else:
            parts.append(
                f"{tag} TEXT (from {document_title}, page {page_number})\n    {content_preview}"
            )

    return "\n\n".join(parts)


def format_sources_list(
    results: List[Any], score_fn: Optional[Callable[[float], float]] = None
) -> str:
    """Format search results as a numbered list of sources.

    Args:
        results: List of SearchResult objects or dicts
        score_fn: Optional function to convert distance to percentage

    Returns:
        Formatted sources list
    """
    if not results:
        return "No sources available."

    lines = []
    for i, r in enumerate(results):
        tag = get_source_tag(r, i)

        # Handle both dataclass and dict results
        if hasattr(r, "source_type"):
            source_type = r.source_type
            element_type = getattr(r, "element_type", None)
            element_label = getattr(r, "element_label", "")
            document_title = getattr(r, "document_title", "Unknown")
            page_number = getattr(r, "page_number", "?")
            score = getattr(r, "score", None)
        else:
            source_type = r.get("source_type", "chunk")
            element_type = r.get("element_type")
            element_label = r.get("element_label", "")
            document_title = r.get("document_title", "Unknown")
            page_number = r.get("page_number", "?")
            score = r.get("score")

        # Format score if available
        score_str = ""
        if score is not None and score_fn:
            score_pct = score_fn(score)
            score_str = f" | {score_pct:.0f}%"

        if source_type == "element" and element_type:
            lines.append(
                f"{tag} {element_type.upper()}: {element_label} "
                f"| {document_title} p.{page_number}{score_str}"
            )
        else:
            lines.append(f"{tag} TEXT chunk | {document_title} p.{page_number}{score_str}")

    return "\n".join(lines)
