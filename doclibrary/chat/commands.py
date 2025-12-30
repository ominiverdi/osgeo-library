"""Command handling for chat CLI."""

import re
from typing import Optional

from doclibrary.config import config
from doclibrary.core.formatting import format_sources_list
from doclibrary.search import get_element_by_id

from .context import ChatContext
from .display import (
    get_display_size_for_element,
    get_element_image_path,
    open_in_viewer,
    show_image,
)


def handle_show_command(ctx: ChatContext, arg: str) -> bool:
    """Handle 'show N' or 'show 1,2,3' command to display elements in terminal.

    Args:
        ctx: Chat context with last results
        arg: Argument string (e.g., "1" or "1,2,3")

    Returns:
        True (command was handled)
    """
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
                elem_type = result.element_type or "element"
                print(f"\n{elem_type.upper()}: {result.element_label}")
                print(f"From: {result.document_title}, page {result.page_number}\n")

                # Get full element data for rendered_path
                element_data = get_element_by_id(result.id)

                # Get appropriate display size and image path
                display_size = get_display_size_for_element(result.element_type)
                full_path = get_element_image_path(result, element_data, config.data_dir)

                show_image(full_path, size=display_size)
            else:
                print(f"\n[{idx + 1}] is a text chunk, no image available.")
                print(f"Content: {result.content[:300]}...")
        else:
            print(f"Invalid index [{idx + 1}]. Use 1-{len(ctx.last_results)}")

    return True


def handle_open_command(ctx: ChatContext, arg: str) -> bool:
    """Handle 'open N' command to open element in GUI viewer.

    Args:
        ctx: Chat context with last results
        arg: Argument string (e.g., "1")

    Returns:
        True (command was handled)
    """
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
    element_data = get_element_by_id(result.id)
    full_path = get_element_image_path(result, element_data, config.data_dir)

    elem_type = result.element_type or "element"
    print(f"\n{elem_type.upper()}: {result.element_label}")
    print(f"From: {result.document_title}, page {result.page_number}\n")

    open_in_viewer(full_path)
    return True


def handle_command(ctx: ChatContext, user_input: str) -> Optional[bool]:
    """Handle special commands.

    Args:
        ctx: Chat context
        user_input: Raw user input

    Returns:
        - True if command was handled
        - False if not a command (process as question)
        - None to exit the chat
    """
    cmd = user_input.lower().strip()

    if cmd in ("quit", "exit", "q"):
        return None

    if cmd == "clear":
        ctx.clear()
        print("Conversation cleared.")
        return True

    if cmd == "sources":
        print("\n" + format_sources_list(ctx.last_results))
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
        print(
            """
Commands:
  show <n>     - Display element in terminal (e.g., 'show 1' or 'show 1,2,3')
  open <n>     - Open element in GUI viewer (requires X11/Wayland)
  sources      - Show sources from last answer
  clear        - Clear conversation history
  help         - Show this help
  quit / exit  - Exit
        """
        )
        return True

    return False  # Not a command, process as question
