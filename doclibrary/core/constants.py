"""Shared constants for doclibrary."""

# System prompt for chat interactions
SYSTEM_PROMPT = """You are a helpful research assistant. Answer questions based ONLY on the provided context.

Rules:
- Be CONCISE: 2-4 paragraphs maximum
- Cite sources inline using [1], [2], [3] etc.
- If the context doesn't have the answer, say so
- Do NOT repeat yourself or list sources at the end

Example: "The Mercator projection [1] preserves angles, making it useful for navigation [2]."
"""

# Element types recognized by the extraction pipeline
ELEMENT_TYPES = frozenset(
    {
        "figure",
        "table",
        "equation",
        "chart",
        "diagram",
    }
)

# Mapping from element type to citation tag prefix
ELEMENT_TAG_MAP = {
    "chunk": "t",  # text
    "figure": "fig",  # figure
    "table": "tab",  # table
    "equation": "eq",  # equation
    "chart": "ch",  # chart
    "diagram": "diag",  # diagram
}

# Colors for annotating bounding boxes (element_type -> RGB)
ANNOTATION_COLORS = {
    "figure": "#FF6B6B",  # Red
    "table": "#4ECDC4",  # Teal
    "equation": "#45B7D1",  # Blue
    "chart": "#96CEB4",  # Green
    "diagram": "#FFEAA7",  # Yellow
    "default": "#DDA0DD",  # Plum (fallback)
}

# Common stopwords to remove from queries for better semantic matching
STOPWORDS = frozenset(
    {
        # Question words
        "what",
        "which",
        "who",
        "whom",
        "where",
        "when",
        "why",
        "how",
        # Prepositions and articles
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "about",
        "a",
        "an",
        "the",
        # Conjunctions
        "and",
        "or",
        "but",
        "if",
        "then",
        # Pronouns
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "my",
        "your",
        "his",
        "her",
        "its",
        "our",
        "their",
        # Common verbs
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "can",
        "could",
        "would",
        "should",
        "may",
        "might",
        "must",
        # Fillers
        "some",
        "any",
        "all",
        "both",
        "each",
        "every",
        "other",
        "another",
        "such",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "also",
        # Query-specific
        "include",
        "includes",
        "including",
        "contain",
        "contains",
        "show",
        "shows",
        "find",
        "search",
        "look",
        "looking",
        "tell",
        "explain",
        "describe",
        "give",
        "get",
        "know",
        "somehow",
        "something",
        "anything",
        "everything",
        "please",
        "help",
        "need",
        "want",
    }
)

# Default PDF rendering DPI
DEFAULT_DPI = 150

# Default chunk size for text splitting
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 200
