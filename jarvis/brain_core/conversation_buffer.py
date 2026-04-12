from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class TurnSummary:
    """Immutable record of a single turn for conversation context."""

    user_text: str
    intent: str
    response_summary: str
    timestamp: str


class ConversationBuffer:
    """Bounded FIFO buffer of recent turn summaries."""

    def __init__(self, max_turns: int = 8) -> None:
        self._max_turns = max_turns
        self._buffer: deque[TurnSummary] = deque(maxlen=max_turns)

    def append(self, summary: TurnSummary) -> None:
        """Add a turn summary. Oldest entry is evicted if at capacity."""

        self._buffer.append(summary)

    def recent(self, n: int = 5) -> list[TurnSummary]:
        """Return the last n turn summaries, oldest first."""

        items = list(self._buffer)
        return items[-n:] if n < len(items) else items

    def clear(self) -> None:
        """Clear all stored turn summaries."""

        self._buffer.clear()

    @property
    def size(self) -> int:
        """Current number of stored summaries."""

        return len(self._buffer)

    @property
    def max_turns(self) -> int:
        """Maximum capacity."""

        return self._max_turns
