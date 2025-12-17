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


# Configuration
LLM_URL = "http://localhost:8080/v1/chat/completions"
LLM_MODEL = "qwen3-30b"
CHAFA_SIZE = "60x25"

# System prompt for the assistant
SYSTEM_PROMPT = """You are a helpful research assistant with access to a library of scientific documents about:
- Map projections and cartography (USGS Snyder manual)
- Computer vision and segmentation (SAM3 paper)
- Alpine habitat monitoring and change detection

When answering questions:
1. Base your answers on the provided context from the documents
2. Be concise but accurate
3. Mention specific figures, tables, or equations when relevant
4. If the context doesn't contain enough information, say so

Do not make up information. Cite the source document when possible."""


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
        response = requests.get(
            LLM_URL.replace("/v1/chat/completions", "/health"), timeout=5
        )
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def query_llm(messages: List[Dict[str, str]], model: str = LLM_MODEL) -> str:
    """Send messages to LLM and get response."""
    try:
        response = requests.post(
            LLM_URL,
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1024,
            },
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


def show_image(path: str) -> bool:
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

    # Check for chafa
    if shutil.which("chafa"):
        try:
            subprocess.run(["chafa", path, "--size", CHAFA_SIZE], check=True)
            print(f"\nPath: {path}")
            return True
        except subprocess.CalledProcessError:
            pass

    # Fallback: just show path
    print(f"Image: {path}")
    print("(Install chafa for inline preview: sudo apt install chafa)")
    return True


def handle_show_command(ctx: ChatContext, arg: str) -> bool:
    """Handle 'show N' or 'show 1,2,3' command to display elements."""
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
                # Build the full path: db/data/{doc_slug}/{crop_path}
                # crop_path is like "elements/filename.png"
                doc_slug = result.document_slug
                full_path = os.path.join("db/data", doc_slug, result.crop_path)
                print(f"\n{result.element_type.upper()}: {result.element_label}")
                print(f"From: {result.document_title}, page {result.page_number}\n")
                show_image(full_path)
            else:
                print(f"\n[{idx + 1}] is a text chunk, no image available.")
                print(f"Content: {result.content[:300]}...")
        else:
            print(f"Invalid index [{idx + 1}]. Use 1-{len(ctx.last_results)}")

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

    if cmd.startswith("show "):
        arg = cmd[5:].strip()
        return handle_show_command(ctx, arg)

    if cmd in ("help", "-h", "--help", "?"):
        print("""
Commands:
  show <n>     - Display element n (e.g., 'show 1' or 'show 1,2,3')
  sources      - Show sources from last answer  
  clear        - Clear conversation history
  help         - Show this help
  quit / exit  - Exit
        """)
        return True

    return False  # Not a command, process as question


def detect_image_request(question: str) -> bool:
    """Detect if user is asking specifically for images/figures/visuals."""
    patterns = [
        r"\b(show|display|see|view)\b.*\b(image|figure|diagram|chart|table|equation|picture|visual)",
        r"\b(image|figure|diagram|chart|table|equation|picture|visual)s?\b.*\b(of|about|related|for)\b",
        r"\bare there\b.*\b(image|figure|diagram|chart|picture|visual)s?\b",
        r"\bwhat\b.*\b(figure|diagram|chart|table)s?\b",
    ]
    q_lower = question.lower()
    return any(re.search(p, q_lower) for p in patterns)


def process_question(ctx: ChatContext, question: str, model: str) -> str:
    """Process a user question: search, build context, query LLM."""
    # Detect if user wants images specifically
    wants_images = detect_image_request(question)

    # Search for relevant content
    print("Searching...", end=" ", flush=True)
    try:
        if wants_images:
            # Prioritize elements when user asks for images
            results = search_elements(question, limit=8)
            if len(results) < 4:
                # Add some text chunks for context
                all_results = search(question, limit=8)
                results = (
                    results + [r for r in all_results if r.source_type == "chunk"][:4]
                )
        else:
            results = search(question, limit=8)
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
    augmented_question = f"""Based on these documents:

{context}

Question: {question}

Answer the question using the provided context. Reference sources using their tags like [t:1] for text, [f:2] for figures, [eq:3] for equations, [tb:4] for tables."""

    # Add to conversation and query LLM
    ctx.add_user_message(augmented_question)

    print("Thinking...", end=" ", flush=True)
    response = query_llm(ctx.get_messages_for_llm(), model)
    print("done.\n")

    ctx.add_assistant_message(response)

    return response


def main():
    parser = argparse.ArgumentParser(description="Chat with OSGeo Library")
    parser.add_argument("--model", default=LLM_MODEL, help="LLM model to use")
    args = parser.parse_args()

    # Check servers
    print("OSGeo Library Chat")
    print("=" * 40)

    if not check_embed_server():
        print("ERROR: Embedding server not running on port 8094")
        print("Start it with: /media/nvme2g-a/llm_toolbox/servers/bge-m3-embed-8094.sh")
        sys.exit(1)
    print("Embedding server: OK")

    if not check_llm_server():
        print("ERROR: LLM server not running on port 8080")
        print("Start Qwen3-30B or another model on port 8080")
        sys.exit(1)
    print(f"LLM server: OK (using {args.model})")

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
        response = process_question(ctx, user_input, args.model)
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
