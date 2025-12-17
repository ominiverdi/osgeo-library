#!/usr/bin/env python3
"""
Interactive CLI chat for OSGeo Library.

Multi-turn conversational RAG with:
- Semantic search over documents
- LLM-powered answers with citations
- Image preview with chafa
- Follow-up questions with context

Usage:
    python chat_cli.py
    python chat_cli.py --model mistral-small  # Use different model

Commands:
    show <n>     - Display element n from last results
    sources      - Show sources from last answer
    clear        - Clear conversation history
    quit/exit    - Exit
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import requests

from search_service import (
    search,
    search_elements,
    SearchResult,
    check_server as check_embed_server,
)
from config import config

# System prompt for the assistant
SYSTEM_PROMPT = """You are a helpful research assistant with access to a library of scientific documents about:
- Map projections and cartography (USGS Snyder manual)
- Computer vision and segmentation (SAM3 paper)
- Alpine habitat monitoring and change detection

When answering questions:
1. Base your answers ONLY on the provided context
2. Be concise but accurate
3. ALWAYS cite sources using the exact tags from the context:
   - [f:N] for figures
   - [tb:N] for tables  
   - [eq:N] for equations
   - [t:N] for text passages
4. If the context doesn't contain enough information, say so

Example: "The Transverse Mercator projection [f:2] shows the cylinder tangent to a meridian [t:1]."

Do not make up information. Always include citation tags in your response."""


@dataclass
class ChatContext:
    """Maintains conversation state."""

    messages: List[Dict[str, str]] = field(default_factory=list)
    last_results: List[SearchResult] = field(default_factory=list)
    last_query: str = ""

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str):
        self.messages.append({"role": "assistant", "content": content})

    def clear(self):
        self.messages = []
        self.last_results = []
        self.last_query = ""

    def get_messages_for_llm(self) -> List[Dict[str, str]]:
        """Get messages formatted for LLM, including system prompt."""
        return [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages[
            -10:
        ]  # Keep last 10 turns


def check_llm_server() -> bool:
    """Check if LLM server is running."""
    try:
        health_url = config.llm_url.replace("/v1/chat/completions", "/health")
        response = requests.get(health_url, timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def query_llm(messages: List[Dict[str, str]], model: str = "") -> str:
    """Send messages to LLM and get response."""
    if not model:
        model = config.llm_model

    try:
        headers = {"Content-Type": "application/json"}
        if config.llm_api_key:
            headers["Authorization"] = f"Bearer {config.llm_api_key}"

        response = requests.post(
            config.llm_url,
            json={
                "model": model,
                "messages": messages,
                "temperature": config.llm_temperature,
                "max_tokens": config.llm_max_tokens,
            },
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        # Remove thinking tags if present (Qwen3 /think mode)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        return f"Error querying LLM: {e}"


def get_source_tag(result: SearchResult) -> str:
    """Get short tag for source type: [t:N] for text, [f:N] for figure, etc."""
    type_map = {
        "chunk": "t",  # text
        "figure": "f",  # figure
        "table": "tb",  # table
        "equation": "eq",  # equation
        "chart": "ch",  # chart
        "diagram": "d",  # diagram
    }
    if result.source_type == "element":
        return type_map.get(result.element_type, "e")
    return "t"


def format_context(results: List[SearchResult]) -> str:
    """Format search results as context for LLM."""
    if not results:
        return "No relevant documents found."

    parts = []
    for i, r in enumerate(results, 1):
        tag = get_source_tag(r)
        if r.source_type == "element":
            parts.append(
                f"[{tag}:{i}] {r.element_type.upper()}: {r.element_label} "
                f"(from {r.document_title}, page {r.page_number})\n"
                f"    {r.content[:500]}"
            )
        else:
            parts.append(
                f"[{tag}:{i}] TEXT (from {r.document_title}, page {r.page_number})\n"
                f"    {r.content[:500]}"
            )

    return "\n\n".join(parts)


def format_sources(results: List[SearchResult]) -> str:
    """Format search results as a numbered list of sources."""
    if not results:
        return "No sources available."

    lines = []
    for i, r in enumerate(results, 1):
        tag = get_source_tag(r)
        score_pct = max(0, (1 - r.score) * 100)
        if r.source_type == "element":
            lines.append(
                f"[{tag}:{i}] {r.element_type.upper()}: {r.element_label} "
                f"| {r.document_title} p.{r.page_number} | {score_pct:.0f}%"
            )
        else:
            lines.append(
                f"[{tag}:{i}] TEXT chunk "
                f"| {r.document_title} p.{r.page_number} | {score_pct:.0f}%"
            )

    return "\n".join(lines)


def has_display() -> bool:
    """Check if graphical display (X11 or Wayland) is available."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def open_in_viewer(path: str) -> bool:
    """Open image in system GUI viewer."""
    if not path:
        print("No image path available.")
        return False

    # Resolve relative path from script directory
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(__file__) or ".", path)

    if not os.path.exists(path):
        print(f"Image not found: {path}")
        return False

    if not has_display():
        print("No display available (X11/Wayland not detected)")
        print("Use 'show N' for terminal preview instead")
        return False

    # Try xdg-open first (works on most Linux systems)
    if shutil.which("xdg-open"):
        subprocess.Popen(
            ["xdg-open", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"Opened: {path}")
        return True

    # Fallback to common image viewers
    viewers = ["feh", "eog", "gwenview", "sxiv", "imv"]
    for viewer in viewers:
        if shutil.which(viewer):
            subprocess.Popen(
                [viewer, path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"Opened with {viewer}: {path}")
            return True

    print("No image viewer found")
    print("Install one of: xdg-utils, feh, eog, gwenview, sxiv, imv")
    return False


def show_image(path: str, size: str = "") -> bool:
    """Display image using chafa if available."""
    if not path:
        print("No image path available.")
        return False

    # Resolve relative path from script directory
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(__file__) or ".", path)

    if not os.path.exists(path):
        print(f"Image not found: {path}")
        return False

    # Use provided size or default from config
    display_size = size or config.chafa_size

    # Check for chafa
    if shutil.which("chafa"):
        try:
            subprocess.run(["chafa", path, "--size", display_size], check=True)
            print(f"\nPath: {path}")
            if has_display():
                print("(Use 'open N' to view in GUI)")
            return True
        except subprocess.CalledProcessError:
            pass

    # Fallback: no chafa available
    print(f"Image: {path}")
    print("(Install chafa for terminal preview: sudo apt install chafa)")
    if has_display():
        print("(Use 'open N' to view in GUI)")
    return True


def handle_show_command(ctx: ChatContext, arg: str) -> bool:
    """Handle 'show N' or 'show 1,2,3' command to display elements."""
    from search_service import get_element_by_id

    if not ctx.last_results:
        print("No results to show. Ask a question first.")
        return True

    # Parse multiple indices: "1,2,3" or "1 2 3"
    indices = []
    for part in re.split(r"[,\s]+", arg):
        part = part.strip()
        if part:
            try:
                indices.append(int(part) - 1)
            except ValueError:
                print(f"Invalid number: {part}")
                return True

    if not indices:
        print("Usage: show <number> or show 1,2,3")
        return True

    for idx in indices:
        if 0 <= idx < len(ctx.last_results):
            result = ctx.last_results[idx]
            if result.source_type == "element" and result.crop_path:
                doc_slug = result.document_slug
                print(f"\n{result.element_type.upper()}: {result.element_label}")
                print(f"From: {result.document_title}, page {result.page_number}\n")

                # Get full element data for rendered_path
                element_data = get_element_by_id(result.id)

                # Choose the best image path and size based on element type
                if result.element_type == "equation":
                    # Prefer rendered image for equations (cleaner LaTeX rendering)
                    if element_data and element_data.get("rendered_path"):
                        image_path = element_data["rendered_path"]
                    else:
                        image_path = result.crop_path
                    full_path = os.path.join(config.data_dir, doc_slug, image_path)
                    show_image(full_path, size=config.chafa_size_equation)
                elif result.element_type == "table":
                    full_path = os.path.join(
                        config.data_dir, doc_slug, result.crop_path
                    )
                    show_image(full_path, size=config.chafa_size_table)
                else:
                    # Figures, charts, diagrams
                    full_path = os.path.join(
                        config.data_dir, doc_slug, result.crop_path
                    )
                    show_image(full_path, size=config.chafa_size)
            else:
                print(f"\n[{idx + 1}] is a text chunk, no image available.")
                print(f"Content: {result.content[:300]}...")
        else:
            print(f"Invalid index [{idx + 1}]. Use 1-{len(ctx.last_results)}")

    return True


def handle_open_command(ctx: ChatContext, arg: str) -> bool:
    """Handle 'open N' command to open element in GUI viewer."""
    from search_service import get_element_by_id

    if not ctx.last_results:
        print("No results to open. Ask a question first.")
        return True

    # Parse index
    try:
        idx = int(arg.strip()) - 1
    except ValueError:
        print(f"Invalid number: {arg}")
        return True

    if not (0 <= idx < len(ctx.last_results)):
        print(f"Invalid index [{idx + 1}]. Use 1-{len(ctx.last_results)}")
        return True

    result = ctx.last_results[idx]

    # Check if it's an element with an image
    if result.source_type != "element" or not result.crop_path:
        print(f"[{idx + 1}] is a text chunk, not an image.")
        print("Use 'show N' to view text content.")
        return True

    # Get the image path
    doc_slug = result.document_slug
    element_data = get_element_by_id(result.id)

    # For equations, prefer rendered image
    if (
        result.element_type == "equation"
        and element_data
        and element_data.get("rendered_path")
    ):
        image_path = element_data["rendered_path"]
    else:
        image_path = result.crop_path

    full_path = os.path.join(config.data_dir, doc_slug, image_path)

    # Resolve relative path
    if not os.path.isabs(full_path):
        full_path = os.path.join(os.path.dirname(__file__) or ".", full_path)

    print(f"\n{result.element_type.upper()}: {result.element_label}")
    print(f"From: {result.document_title}, page {result.page_number}\n")

    open_in_viewer(full_path)
    return True


def handle_command(ctx: ChatContext, user_input: str) -> Optional[bool]:
    """
    Handle special commands.
    Returns True if command handled, False to continue, None to exit.
    """
    cmd = user_input.lower().strip()

    if cmd in ("quit", "exit", "q"):
        return None

    if cmd == "clear":
        ctx.clear()
        print("Conversation cleared.")
        return True

    if cmd == "sources":
        print("\n" + format_sources(ctx.last_results))
        return True

    # Handle "show N" command (terminal preview)
    if cmd == "show" or cmd.startswith("show "):
        if cmd == "show":
            print("Usage: show <number> or show 1,2,3")
            return True
        arg = cmd[5:].strip()
        if arg:
            return handle_show_command(ctx, arg)
        print("Usage: show <number> or show 1,2,3")
        return True

    # Handle "open N" command (GUI viewer)
    if cmd == "open" or cmd.startswith("open "):
        if cmd == "open":
            print("Usage: open <number>")
            return True
        arg = cmd[5:].strip()
        if arg:
            return handle_open_command(ctx, arg)
        print("Usage: open <number>")
        return True

    if cmd in ("help", "-h", "--help", "?"):
        print("""
Commands:
  show <n>     - Display element in terminal (e.g., 'show 1' or 'show 1,2,3')
  open <n>     - Open element in GUI viewer (requires X11/Wayland)
  sources      - Show sources from last answer
  clear        - Clear conversation history
  help         - Show this help
  quit / exit  - Exit
        """)
        return True

    return False  # Not a command, process as question


def detect_element_request(question: str) -> bool:
    """Detect if user is asking for elements (figures, tables, equations, etc.)."""
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
    """Expand follow-up queries by combining with previous query context."""
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
    # These indicate the query refers to a previous topic
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
        # Remove the referential phrase and combine with last query
        cleaned = re.sub(
            r"\b(related to|about|for|of|on)\s+(this|that|it|these|those)\b",
            "",
            q_lower,
        ).strip()
        # Clean up punctuation and extra spaces
        cleaned = re.sub(r"[?\s]+", " ", cleaned).strip()
        return f"{cleaned} {last_query}"

    return question


def process_question(ctx: ChatContext, question: str, model: str) -> str:
    """Process a user question: search, build context, query LLM."""
    # Detect if user wants elements (figures, equations, tables, etc.)
    wants_elements = detect_element_request(question)

    # Expand follow-up queries with previous context
    search_query = expand_followup_query(question, ctx.last_query)
    if search_query != question:
        print(f"(Expanded query: {search_query})")

    # Search for relevant content
    print("Searching...", end=" ", flush=True)
    try:
        if wants_elements:
            # Prioritize elements when user asks for figures/equations/tables
            results = search_elements(search_query, limit=8)
            if len(results) < 4:
                # Add some text chunks for context
                all_results = search(search_query, limit=8)
                results = (
                    results + [r for r in all_results if r.source_type == "chunk"][:4]
                )
        else:
            results = search(search_query, limit=8)
        ctx.last_results = results
        ctx.last_query = question
        element_count = sum(1 for r in results if r.source_type == "element")
        print(f"found {len(results)} results ({element_count} elements).")
    except Exception as e:
        print(f"Search error: {e}")
        return "I couldn't search the documents. Is the embedding server running?"

    # Build context for LLM
    context = format_context(results)

    # Create the augmented prompt
    augmented_question = f"""Context (cite using the tags shown):

{context}

Question: {question}

IMPORTANT: Include citation tags like [f:1], [t:2], [eq:3], [tb:4] in your answer to reference the sources above."""

    # Add to conversation and query LLM
    ctx.add_user_message(augmented_question)

    print("Thinking...", end=" ", flush=True)
    response = query_llm(ctx.get_messages_for_llm(), model)
    print("done.\n")

    ctx.add_assistant_message(response)

    return response


def main():
    parser = argparse.ArgumentParser(description="Chat with OSGeo Library")
    parser.add_argument(
        "--model", default=None, help="LLM model to use (default from config)"
    )
    args = parser.parse_args()

    # Use config default if not specified
    model = args.model or config.llm_model

    # Check servers
    print("OSGeo Library Chat")
    print("=" * 40)

    if not check_embed_server():
        print(f"ERROR: Embedding server not running at {config.embed_url}")
        sys.exit(1)
    print("Embedding server: OK")

    if not check_llm_server():
        print(f"ERROR: LLM server not running at {config.llm_url}")
        sys.exit(1)
    print(f"LLM server: OK (using {model})")

    print("\nType 'help' for commands, 'quit' to exit.\n")

    ctx = ChatContext()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Check for commands
        cmd_result = handle_command(ctx, user_input)
        if cmd_result is None:  # Exit
            print("Goodbye!")
            break
        if cmd_result is True:  # Command handled
            continue

        # Process as question
        response = process_question(ctx, user_input, model)
        print(f"Assistant: {response}\n")

        # Show available sources hint
        if ctx.last_results:
            elements = [r for r in ctx.last_results if r.source_type == "element"]
            if elements:
                print(
                    f"(Type 'sources' for references, 'show N' for images - [f:], [tb:], [eq:] can be shown)\n"
                )


if __name__ == "__main__":
    main()
