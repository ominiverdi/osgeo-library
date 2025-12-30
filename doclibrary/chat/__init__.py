"""Chat functionality for doclibrary."""

from .context import ChatContext
from .commands import handle_command, handle_show_command, handle_open_command
from .display import show_image, open_in_viewer, has_display
from .query import process_question, expand_followup_query, detect_element_request

__all__ = [
    # Context
    "ChatContext",
    # Commands
    "handle_command",
    "handle_show_command",
    "handle_open_command",
    # Display
    "show_image",
    "open_in_viewer",
    "has_display",
    # Query
    "process_question",
    "expand_followup_query",
    "detect_element_request",
]
