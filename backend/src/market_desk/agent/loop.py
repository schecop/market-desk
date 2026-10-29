"""The hand-written tool-use loop: the agent itself.

Send the conversation and the tool definitions to Claude. If it answers, stop. If it asks for
tools (`tool_use` blocks), run them, send the results back (`tool_result` blocks) and ask again.

The loop doesn't store anything: it takes the message list, extends it in place and returns.
Saving the conversation and committing the session are the caller's job (`POST /chat`, task 5).
"""

from dataclasses import dataclass, field
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

        pending = []
        tool_blocks = [block for block in response.content if block.type == "tool_use"]
        for tool_block in tool_blocks:
            if _is_write(tool_block):
                pending.append(tool_block)

        if pending:
            return AgentResult(
                status="awaiting_approval",
                answer=_text(response),
                steps=steps,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                pending=pending,
            )

        # One assistant turn can ask for several tools. All the results go back in ONE user
        # message: splitting them teaches Claude to stop making parallel calls.
        results = [await _run_tool(ctx, block) for block in tool_blocks]
        messages.append({"role": "user", "content": results})

    return AgentResult(
        status="step_limit",
        answer=_text(response),
        steps=steps,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
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
    # 1. Take the tool_use blocks from the last message (check it's an assistant turn).
    last_message = messages[-1]
    if last_message["role"] != "assistant":
        raise ValueError("Last message is not from an assistant")

    tool_use_blocks = [
        block for block in last_message["content"] if isinstance(block, ToolUseBlock)
    ]
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
        if block.id not in write_ids:
            results.append(await _run_tool(ctx, block))
        else:
            if decisions[block.id]:
                results.append(await _run_tool(ctx, block))
            else:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": DECLINED,
                        "is_error": True,
                    }
                )

    # 4. Append them as ONE user message, then let the normal loop continue (run_agent).
    messages.append({"role": "user", "content": results})
    return await run_agent(client, ctx, messages, max_steps)


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
