"""Text processing utilities for doclibrary."""

import re
from typing import Optional


def extract_latex_from_description(description: str) -> Optional[str]:
    """Extract LaTeX from element description.

    The vision model typically returns equations with descriptions like:
    - "LaTeX: \\sin x + \\cos y"
    - "Formula for computing P: LaTeX: P = (cos phi / cos phi_g)..."

    Args:
        description: Element description that may contain LaTeX

    Returns:
        Extracted LaTeX string, or None if not found
    """
    if not description:
        return None

    # Look for 'LaTeX:' prefix (case insensitive)
    match = re.search(r"LaTeX:\s*(.+)", description, re.IGNORECASE | re.DOTALL)
    if match:
        latex = match.group(1).strip()
        # Clean up: stop at sentence boundary (new sentence starts with capital)
        latex = re.split(r"\.\s+[A-Z]", latex)[0]
        return latex

    return None


def clean_line_numbers(text: str) -> str:
    """Remove margin line numbers from text (e.g., ICLR format: 000, 001, 002...).

    Academic paper submissions often have line numbers in margins for reviewer
    reference. This function detects and removes consistent 3-digit line number
    patterns at the start of lines.

    Args:
        text: Text that may contain line numbers

    Returns:
        Text with line numbers removed
    """
    if not text:
        return text

    lines = text.split("\n")

    # Check if we have a consistent line number pattern
    # Look for 3-digit numbers at the start of lines
    line_num_pattern = re.compile(r"^\s*(\d{3})\s+")

    numbered_lines = 0
    for line in lines[:20]:  # Check first 20 lines
        if line_num_pattern.match(line):
            numbered_lines += 1

    # If more than half of the first 20 lines have line numbers, remove them
    if numbered_lines > 10:
        cleaned_lines = []
        for line in lines:
            cleaned = line_num_pattern.sub("", line)
            cleaned_lines.append(cleaned)
        return "\n".join(cleaned_lines)

    return text


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text for chunking.

    - Collapses multiple spaces to single space
    - Normalizes multiple newlines to double newline (paragraph break)
    - Strips leading/trailing whitespace

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    if not text:
        return text

    # Collapse multiple spaces to single
    text = re.sub(r" +", " ", text)

    # Normalize newlines: 3+ newlines -> 2 newlines (paragraph break)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip whitespace from each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def extract_keywords(query: str) -> str:
    """Extract keywords from a natural language query.

    Removes stopwords while preserving:
    - Capitalized words (likely proper nouns)
    - Technical terms

    Args:
        query: Natural language query string

    Returns:
        Space-separated keywords
    """
    from .constants import STOPWORDS

    words = query.split()
    keywords = []

    for word in words:
        # Keep capitalized words (proper nouns like "Adam Stewart")
        if word[0].isupper() and word.lower() not in STOPWORDS:
            keywords.append(word)
        # Keep non-stopwords
        elif word.lower() not in STOPWORDS:
            keywords.append(word)

    return " ".join(keywords)


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Truncate text to maximum length at word boundary.

    Args:
        text: Text to truncate
        max_length: Maximum length (default 500)
        suffix: Suffix to add if truncated (default "...")

    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text

    # Find last space before max_length
    truncated = text[: max_length - len(suffix)]
    last_space = truncated.rfind(" ")

    if last_space > max_length // 2:
        truncated = truncated[:last_space]

    return truncated + suffix
