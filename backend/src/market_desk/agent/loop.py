"""The hand-written tool-use loop: the agent itself.

Send the conversation and the tool definitions to Claude. If it answers, stop. If it asks for
tools (`tool_use` blocks), run them, send the results back (`tool_result` blocks) and ask again.

The loop doesn't store anything: it takes the message list, extends it in place and returns.
Saving the conversation and committing the session are the caller's job (`POST /chat`).

Two ways to call it: `stream_agent` yields an event as each step happens (the API streams them),
`run_agent` waits and returns only the result. Same loop: `run_agent` just consumes the stream.
"""

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam, ToolResultBlockParam, ToolUseBlock
from pydantic import ValidationError

from market_desk.agent.events import AgentEvent, AssistantTurn, Done, ToolResult
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

# Why a run ended: Claude's own stop_reason, our step limit, or a write tool waiting for a human
Status = Literal["done", "max_tokens", "refusal", "step_limit", "awaiting_approval", "other"]

# The tool_result a rejected write gets: an error, so the model knows the action didn't happen
DECLINED = "The user declined this action. Don't retry it unless the user asks again."


@dataclass
class AgentResult:
    status: Status
    answer: str  # the text of the last response ("" if there was none)
    steps: int  # model calls made
    input_tokens: int
    output_tokens: int
    # With status "awaiting_approval": the write calls a human must approve or reject
    pending: list[ToolUseBlock] = field(default_factory=list)

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
    return await _final(stream_agent(client, ctx, messages, max_steps))


async def stream_agent(
    client: AsyncAnthropic, ctx: ToolContext, messages: list[MessageParam], max_steps: int = 8
) -> AsyncIterator[AgentEvent]:
    """Like run_agent, but yields an event as each step happens, and Done(result) last.

    An async generator: nothing runs until the caller iterates it, and each `yield` hands one
    event over and pauses here until the caller asks for the next one.
    """
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
        yield AssistantTurn(
            content=response.content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        if response.stop_reason != "tool_use":
            # A generator can't `return value`: the result travels in the last event instead
            yield Done(
                AgentResult(
                    status=_status(response),
                    answer=_text(response),
                    steps=steps,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            )
            return

        pending = []
        tool_blocks = [block for block in response.content if block.type == "tool_use"]
        for tool_block in tool_blocks:
            if _is_write(tool_block):
                pending.append(tool_block)

        if pending:
            yield Done(
                AgentResult(
                    status="awaiting_approval",
                    answer=_text(response),
                    steps=steps,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    pending=pending,
                )
            )
            return

        # One assistant turn can ask for several tools. All the results go back in ONE user
        # message: splitting them teaches Claude to stop making parallel calls.
        results = []
        for block in tool_blocks:
            result, event = await _run_tool_timed(ctx, block)
            results.append(result)
            yield event
        messages.append({"role": "user", "content": results})

    yield Done(
        AgentResult(
            status="step_limit",
            answer=_text(response),
            steps=steps,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    )


async def resume_agent(
    client: AsyncAnthropic,
    ctx: ToolContext,
    messages: list[MessageParam],
    decisions: dict[str, bool],
    max_steps: int = 8,
) -> AgentResult:
    """Continue a run that stopped with "awaiting_approval". Extends `messages` in place.

    `messages` must end on the assistant turn that asked for the tools. `decisions` maps each
    pending write call's tool_use_id to True (approved) or False (rejected). Approved calls
    run exactly as Claude proposed them: an approver can't change the arguments.
    """
    return await _final(stream_resume(client, ctx, messages, decisions, max_steps))


async def stream_resume(
    client: AsyncAnthropic,
    ctx: ToolContext,
    messages: list[MessageParam],
    decisions: dict[str, bool],
    max_steps: int = 8,
) -> AsyncIterator[AgentEvent]:
    """Like resume_agent, but yields events (see stream_agent). Checks run before any event."""
    # 1. Take the tool_use blocks from the last message (check it's an assistant turn).
    last_message = messages[-1]
    if last_message["role"] != "assistant":
        raise ValueError("Last message is not from an assistant")

    candidates = (_as_tool_use(block) for block in last_message["content"])
    tool_use_blocks = [block for block in candidates if block is not None]

    if not tool_use_blocks:
        raise ValueError("No tool_use blocks found")
    write_ids = {block.id for block in tool_use_blocks if _is_write(block)}

    # 2. Decisions must match this turn's write calls exactly, checked before anything runs.
    #    Set differences name every offending id at once, not just the first.
    undecided = write_ids - decisions.keys()
    if undecided:
        raise ValueError(f"Every write tool call needs a decision; missing: {sorted(undecided)}")
    # A decision for an id that isn't a write call here (an older turn, a read tool) would be
    # ignored, and the reviewer would think they decided something they didn't.
    unexpected = decisions.keys() - write_ids
    if unexpected:
        raise ValueError(f"Decisions for ids that aren't pending writes: {sorted(unexpected)}")

    # 3. Build one tool_result per tool_use block, in order: reads and approved writes run
    #    through _run_tool; rejected writes get DECLINED with is_error=True.
    results = []
    for block in tool_use_blocks:
        # Reads and unknown tools: _run_tool turns an unknown name into an error result
        if block.id not in write_ids or decisions[block.id]:
            result, event = await _run_tool_timed(ctx, block)
        else:
            result = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": DECLINED,
                "is_error": True,
            }
            event = ToolResult(
                block.id, block.name, DECLINED, is_error=True, duration_ms=None, declined=True
            )
        results.append(result)
        yield event

    # 4. Append them as ONE user message, then let the normal loop continue (stream_agent).
    messages.append({"role": "user", "content": results})
    # `async for ... yield` passes every event of the inner generator through, Done included
    async for next_event in stream_agent(client, ctx, messages, max_steps):
        yield next_event


async def _final(events: AsyncIterator[AgentEvent]) -> AgentResult:
    """Run a stream to the end and return its result: what the non-streaming callers want."""
    async for event in events:
        if isinstance(event, Done):
            return event.result
    raise RuntimeError("The agent stream ended without a Done event")


async def _run_tool_timed(
    ctx: ToolContext, block: ToolUseBlock
) -> tuple[ToolResultBlockParam, ToolResult]:
    """_run_tool, plus the event that reports it (with how long it took)."""
    start = time.perf_counter()  # a monotonic clock: unaffected if the system time changes
    result = await _run_tool(ctx, block)
    duration_ms = round((time.perf_counter() - start) * 1000)
    event = ToolResult(
        tool_use_id=block.id,
        name=block.name,
        content=str(result["content"]),
        is_error=result.get("is_error", False),
        duration_ms=duration_ms,
    )
    return result, event


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


def _as_tool_use(block: Any) -> ToolUseBlock | None:
    """A tool_use block as an SDK object, whichever shape it arrived in; None for other blocks.

    Fresh from Claude, blocks are SDK objects; reloaded from Postgres, they're plain dicts.
    """
    # Any: a block can be an SDK model of several types or a dict, and we check it here anyway
    if isinstance(block, ToolUseBlock):
        return block
    if isinstance(block, dict) and block.get("type") == "tool_use":
        return ToolUseBlock.model_validate(block)
    return None


def _is_write(block: ToolUseBlock) -> bool:
    """A known tool that changes state. A made-up name is not a write: it gets an error result."""
    tool = TOOLS.get(block.name)
    return tool is not None and tool.writes


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
