"""What a tool is: a contract the model reads plus a typed function we run.

The model never runs code. It sees each tool's name, description and input schema, answers
with a `tool_use` block (a name and arguments it generated), and we validate and execute it.
These definitions are protocol-neutral: the hand-written loop, the LangGraph version and the
MCP server all wrap the same Tool objects.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from market_desk.clients.cala import CalaClient
from market_desk.clients.edgar import EdgarClient


class ToolError(Exception):
    """A failure the model should read and react to ("no company named X"), not a crash.

    The message is written for the model: say what went wrong and what to try instead.
    """


@dataclass
class ToolContext:
    """Everything a tool needs from outside, injected so tests can pass fakes."""

    session: Session
    cala: CalaClient
    edgar: EdgarClient


@dataclass(frozen=True)
class Tool:
    name: str
    # Part of the prompt: the model picks a tool by its description, so say when to use it
    # and when not to.
    description: str
    input_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], Awaitable[BaseModel]]
    # Write tools change state; the API asks a human before running them (task 4)
    writes: bool = False

    def definition(self) -> dict[str, Any]:
        """The tool as the Claude API expects it in `tools=[...]`."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }

    async def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> str:
        """Validate the model's arguments, run the handler, return JSON for the tool_result.

        Raises pydantic.ValidationError for bad arguments, ToolError or a client error for a
        failed call. Turning those into an error tool_result is the loop's job.
        """
        params = self.input_model.model_validate(arguments)
        result = await self.handler(ctx, params)
        # exclude_none: every byte returned is input tokens on the next turn
        return result.model_dump_json(exclude_none=True)
