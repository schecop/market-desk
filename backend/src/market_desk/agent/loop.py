"""The hand-written tool-use loop: the agent itself.

Send the conversation and the tool definitions to Claude. If it answers, stop. If it asks for
tools (`tool_use` blocks), run them, send the results back (`tool_result` blocks) and ask again.

The loop doesn't store anything: it takes the message list, extends it in place and returns.
Saving the conversation and committing the session are the caller's job (`POST /chat`, task 5).
"""

from dataclasses import dataclass
from typing import Literal

from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam, ToolResultBlockParam, ToolUseBlock
from pydantic import ValidationError

from market_desk.clients.cala import CalaError
from market_desk.clients.edgar import EdgarError
from market_desk.tools import TOOLS, ToolContext, ToolError

MODEL = "claude-sonnet-5-5"
INPUT_USD_PER_MTOK = 2.0
OUTPUT_USD_PER_MTOK = 10.0
# Per response, not per run. High enough that a long answer isn't cut off mid-sentence.
MAX_TOKENS = 16_000

SYSTEM_PROMPT = """\
You are Market Desk, a research assistant for questions about US public companies.
Answer from tool results, not from memory: use get_company_facts for exact facts and
relationships, search_filings for what a company says about itself in its SEC filings.
Say which tool each fact came from. If the tools can't answer, say so plainly."""

# Why a run ended: Claude's own stop_reason, or our step limit
Status = Literal["done", "max_tokens", "refusal", "step_limit", "other"]


@dataclass
class AgentResult:
    status: Status
    answer: str  # the text of the last response ("" if there was none)
    steps: int  # model calls made
    input_tokens: int
    output_tokens: int

    @property
    def input_tokens_usd(self) -> float:
        return self.input_tokens * INPUT_USD_PER_MTOK / 1_000_000

    @property
    def output_tokens_usd(self) -> float:
        return self.output_tokens * OUTPUT_USD_PER_MTOK / 1_000_000


async def run_agent(
    client: AsyncAnthropic, ctx: ToolContext, messages: list[MessageParam], max_steps: int = 8
) -> AgentResult:
    """Run the conversation in `messages` until Claude answers. Extends `messages` in place."""
    if max_steps < 1:
        raise ValueError(f"max_steps should be greater than 0, got {max_steps}")

    tools = [tool.definition() for tool in TOOLS.values()]
    steps = 0
    input_tokens = 0
    output_tokens = 0

    while steps < max_steps:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools,  # type: ignore[arg-type]  # our dicts match ToolParam's shape
            messages=messages,
        )
        steps += 1
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        # The whole content goes back unchanged: text, tool_use and thinking blocks. Claude
        # reads its own earlier turns, and thinking blocks are rejected if they're edited.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return AgentResult(
                status=_status(response),
                answer=_text(response),
                steps=steps,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        # One assistant turn can ask for several tools. All the results go back in ONE user
        # message: splitting them teaches Claude to stop making parallel calls.
        results = [
            await _run_tool(ctx, block) for block in response.content if block.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})

    return AgentResult(
        status="step_limit",
        answer=_text(response),
        steps=steps,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


async def _run_tool(ctx: ToolContext, block: ToolUseBlock) -> ToolResultBlockParam:
    """Run one tool call and wrap its output as the tool_result Claude expects.

    One after another, not concurrently: all tools share one SQLAlchemy session, and a
    session can't be used by two coroutines at once.
    """
    if block.name not in TOOLS:
        available = ", ".join(TOOLS)  # iterating a dict gives its keys
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": f"Tool {block.name} is not available. Available tools are: {available}",
            "is_error": True,
        }

    tool = TOOLS[block.name]
    try:
        # A savepoint per tool call: if the tool raises, its partial writes are rolled back (the
        # `with` block does that and re-raises), and earlier tools' writes stay.
        with ctx.session.begin_nested():
            output = await tool.run(ctx, block.input)
    except (ValidationError, ToolError, CalaError, EdgarError) as err:
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": str(err),
            "is_error": True,
        }

    return {"type": "tool_result", "tool_use_id": block.id, "content": output}


def _status(response: Message) -> Status:
    match response.stop_reason:
        case "end_turn":
            return "done"
        case "max_tokens" | "refusal":
            return response.stop_reason
        case _:
            return "other"


def _text(response: Message) -> str:
    return "".join(block.text for block in response.content if block.type == "text")
