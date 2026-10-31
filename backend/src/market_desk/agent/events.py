"""What the loop reports while it runs: one event per thing that happened, in order.

The loop yields these; the API turns them into Server-Sent Events and saves the conversation.
They describe the agent, not HTTP: nothing here knows about SSE or the database.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from anthropic.types import ContentBlock

if TYPE_CHECKING:  # loop.py imports this module, so a runtime import would be circular
    from market_desk.agent.loop import AgentResult


@dataclass(frozen=True)
class AssistantTurn:
    """Claude answered once: its content blocks (text, tool_use...) and what that call cost."""

    # Sequence, not list: read-only, so it also accepts the stream's ParsedTextBlock subclasses
    content: Sequence[ContentBlock]
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ToolResult:
    """A tool call finished: ran (successfully or not), or was declined by a human."""

    tool_use_id: str
    name: str
    content: str
    is_error: bool
    duration_ms: int | None  # None when it didn't run (declined)
    declined: bool = False  # a human rejected it: is_error is True too, so Claude knows


@dataclass(frozen=True)
class TextDelta:
    """A piece of a Claude answer, obtained while generating the whole answer."""

    text: str


@dataclass(frozen=True)
class Done:
    """The run ended. Always the last event, exactly once."""

    result: "AgentResult"


AgentEvent = AssistantTurn | ToolResult | TextDelta | Done
