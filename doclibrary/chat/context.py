"""Chat context management for doclibrary."""

from dataclasses import dataclass, field
from typing import Dict, List

from doclibrary.core.constants import SYSTEM_PROMPT
from doclibrary.search.service import SearchResult


@dataclass
class ChatContext:
    """Maintains conversation state for multi-turn chat."""

    messages: List[Dict[str, str]] = field(default_factory=list)
    last_results: List[SearchResult] = field(default_factory=list)
    last_query: str = ""

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation."""
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation."""
        self.messages.append({"role": "assistant", "content": content})

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages = []
        self.last_results = []
        self.last_query = ""

    def get_messages_for_llm(self, max_turns: int = 10) -> List[Dict[str, str]]:
        """Get messages formatted for LLM, including system prompt.

        Args:
            max_turns: Maximum number of conversation turns to include

        Returns:
            List of message dicts with system prompt prepended
        """
        return [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages[-max_turns * 2 :]

    @property
    def has_results(self) -> bool:
        """Check if there are results from the last search."""
        return len(self.last_results) > 0

    @property
    def element_count(self) -> int:
        """Count of element results (figures, tables, equations)."""
        return sum(1 for r in self.last_results if r.source_type == "element")

    @property
    def chunk_count(self) -> int:
        """Count of text chunk results."""
        return sum(1 for r in self.last_results if r.source_type == "chunk")
