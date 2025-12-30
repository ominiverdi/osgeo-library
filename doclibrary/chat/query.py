"""Query processing for chat - search, context building, LLM interaction."""

import re
from typing import List, Optional

from doclibrary.config import config
from doclibrary.core.formatting import format_context_for_llm
from doclibrary.core.llm import query_llm
from doclibrary.search import search, search_elements, SearchResult

from .context import ChatContext


def detect_element_request(question: str) -> bool:
    """Detect if user is asking for elements (figures, tables, equations, etc.).

    Args:
        question: User's question

    Returns:
        True if the question is about visual elements
    """
    q_lower = question.lower()

    # Direct element type mentions
    element_keywords = [
        r"\b(formula|formulas|equation|equations)\b",
        r"\b(figure|figures|diagram|diagrams|chart|charts)\b",
        r"\b(table|tables)\b",
        r"\b(image|images|picture|pictures|visual|visuals)\b",
    ]

    # Contextual patterns
    contextual_patterns = [
        r"\b(show|display|see|view)\b.*\b(image|figure|diagram|chart|table|equation|picture|visual|formula)",
        r"\b(image|figure|diagram|chart|table|equation|picture|visual|formula)s?\b.*\b(of|about|related|for)\b",
        r"\bare there\b.*\b(image|figure|diagram|chart|picture|visual|formula|equation)s?\b",
        r"\bwhat\b.*\b(figure|diagram|chart|table|formula|equation)s?\b",
    ]

    # Check for element keywords
    for pattern in element_keywords:
        if re.search(pattern, q_lower):
            return True

    # Check contextual patterns
    for pattern in contextual_patterns:
        if re.search(pattern, q_lower):
            return True

    return False


def expand_followup_query(question: str, last_query: str) -> str:
    """Expand follow-up queries by combining with previous query context.

    Args:
        question: Current question
        last_query: Previous query for context

    Returns:
        Expanded query string
    """
    if not last_query:
        return question

    q_lower = question.lower().strip()

    # Patterns that indicate a follow-up/clarification (at start of query)
    prefix_followup_patterns = [
        r"^i mean[t]?\b",
        r"^actually\b",
        r"^no[,.]?\s",
        r"^not that[,.]?\s",
        r"^what about\b",
        r"^how about\b",
        r"^and\b",
        r"^or\b",
        r"^but\b",
    ]

    # Patterns with referential pronouns (this, that, it, these, those)
    referential_patterns = [
        r"\b(related to|about|for|of|on)\s+(this|that|it|these|those)\b",
        r"\b(this|that)\s+(topic|subject|projection|method)\b",
        r"\bany\b.*\b(related|about|for)\b.*\b(this|that|it)\b",
        r"^(any|are there|show me|what)\b.*\b(this|that|it)\s*\??$",
    ]

    is_prefix_followup = any(re.match(p, q_lower) for p in prefix_followup_patterns)
    is_referential = any(re.search(p, q_lower) for p in referential_patterns)

    if is_prefix_followup:
        # Remove the follow-up prefix to get the clarification
        cleaned = re.sub(
            r"^(i mean[t]?|actually|no[,.]?|not that[,.]?|what about|how about|and|or|but)\s*",
            "",
            q_lower,
        ).strip()
        if cleaned:
            return f"{cleaned} {last_query}"

    elif is_referential:
        # Replace referential pronouns with the last query topic
        cleaned = re.sub(
            r"\b(related to|about|for|of|on)\s+(this|that|it|these|those)\b",
            "",
            q_lower,
        ).strip()
        # Clean up punctuation and extra spaces
        cleaned = re.sub(r"[?\s]+", " ", cleaned).strip()
        return f"{cleaned} {last_query}"

    return question


def process_question(
    ctx: ChatContext,
    question: str,
    model: Optional[str] = None,
    verbose: bool = True,
) -> str:
    """Process a user question: search, build context, query LLM.

    Args:
        ctx: Chat context object
        question: User's question
        model: LLM model to use (default from config)
        verbose: Print progress messages

    Returns:
        LLM response string
    """
    if model is None:
        model = config.llm_model

    # Detect if user wants elements (figures, equations, tables, etc.)
    wants_elements = detect_element_request(question)

    # Expand follow-up queries with previous context
    search_query = expand_followup_query(question, ctx.last_query)
    if search_query != question and verbose:
        print(f"(Expanded query: {search_query})")

    # Search for relevant content
    if verbose:
        print("Searching...", end=" ", flush=True)

    try:
        if wants_elements:
            # Prioritize elements when user asks for figures/equations/tables
            results = search_elements(search_query, limit=8)
            if len(results) < 4:
                # Add some text chunks for context
                all_results = search(search_query, limit=8)
                results = results + [r for r in all_results if r.source_type == "chunk"][:4]
        else:
            results = search(search_query, limit=8)

        ctx.last_results = results
        ctx.last_query = question

        if verbose:
            element_count = sum(1 for r in results if r.source_type == "element")
            print(f"found {len(results)} results ({element_count} elements).")

    except Exception as e:
        if verbose:
            print(f"Search error: {e}")
        return "I couldn't search the documents. Is the embedding server running?"

    # Build context for LLM
    context = format_context_for_llm(results)

    # Create the augmented prompt
    augmented_question = f"""Context (cite using the tags shown):

{context}

Question: {question}

IMPORTANT: Include citation tags like [f:1], [t:2], [eq:3], [tb:4] in your answer to reference the sources above."""

    # Add to conversation and query LLM
    ctx.add_user_message(augmented_question)

    if verbose:
        print("Thinking...", end=" ", flush=True)

    response = query_llm(ctx.get_messages_for_llm(), model)

    if verbose:
        print("done.\n")

    ctx.add_assistant_message(response)

    return response
