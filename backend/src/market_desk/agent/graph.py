"""The same agent as loop.py, as a LangGraph state graph: for comparing the two (ADR-0009).

    START -> call_model --(answered)--> END
                 |--(reads only)--> run_tools --(steps left)--> call_model
                 |                      '--(step limit)--> END
                 '--(a write)--> approve --interrupt()--> run_tools

The loop's `while` and `if`s become nodes (functions that return state changes) and edges
(functions that pick the next node). The tools and their error handling are loop.py's.

The big difference is pausing. loop.py stops and returns; resuming rebuilds everything from
the messages. Here `interrupt()` freezes the run in a checkpointer (saved state, per
thread_id), and `Command(resume=decisions)` continues it from inside the `approve` node.
"""

import operator
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict, cast

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, ToolResultBlockParam, ToolUseBlock
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

# Shared with the hand-written loop on purpose: only the control flow differs
from market_desk.agent.events import AgentEvent, AssistantTurn, Done, TextDelta, ToolResult
from market_desk.agent.loop import (
    DECLINED,
    MAX_TOKENS,
    MODEL,
    SYSTEM_PROMPT,
    AgentResult,
    Status,
    _is_write,
    _run_tool_timed,
)
from market_desk.tools import TOOLS, ToolContext


class AgentState(TypedDict):
    """What the checkpointer saves between steps, so plain JSON-ready data only."""

    # A reducer: a node returns only the messages it adds, and operator.add appends them.
    # Without one, a returned key replaces the old value (as for the counters below).
    messages: Annotated[list[MessageParam], operator.add]
    steps: int
    input_tokens: int
    output_tokens: int
    stop_reason: str | None  # of the last model call
    decisions: dict[str, bool]  # set by `approve`, read by `run_tools`


@dataclass
class GraphContext:
    """Per-run things that aren't state: live clients and a DB session can't be saved in a
    checkpoint. Passed with `context=` on every call and read in nodes as `runtime.context`.
    """

    claude: AsyncAnthropic
    tools: ToolContext
    max_steps: int


# --- nodes: each takes the state and returns the changes ---


async def call_model(state: AgentState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    ctx = runtime.context
    async with ctx.claude.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=[tool.definition() for tool in TOOLS.values()],  # type: ignore[misc]
        messages=state["messages"],
    ) as stream:
        async for text in stream.text_stream:
            runtime.stream_writer(TextDelta(text))  # read by stream_mode="custom"
        response = await stream.get_final_message()

    usage = response.usage
    runtime.stream_writer(AssistantTurn(response.content, usage.input_tokens, usage.output_tokens))
    # Stored as dicts, not SDK objects: the checkpoint is serialized
    content = [block.model_dump(mode="json", exclude_none=True) for block in response.content]
    return {
        "messages": [{"role": "assistant", "content": content}],
        "steps": state["steps"] + 1,
        "input_tokens": state["input_tokens"] + usage.input_tokens,
        "output_tokens": state["output_tokens"] + usage.output_tokens,
        "stop_reason": response.stop_reason,
    }


async def approve(state: AgentState) -> dict[str, Any]:
    """Pause until a human decides every write call of the last turn.

    On resume this node runs AGAIN from the top, and interrupt() then returns the decisions
    instead of pausing. So everything before it must be safe to run twice (it only reads).

    The decisions were checked before resuming (GraphAgent.stream_resume), not here: the
    checkpoint saves a resume value before the node runs, so if this node rejected it, every
    later resume would replay the same bad value and the run would be stuck.
    """
    write_ids = {call.id for call in _tool_calls(state) if _is_write(call)}
    answer = interrupt({"pending": sorted(write_ids)})
    return {"decisions": answer["decisions"]}


async def run_tools(state: AgentState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    """Every call of the last turn, in order; all results in ONE user message (see loop.py)."""
    results: list[ToolResultBlockParam] = []
    for call in _tool_calls(state):
        if _is_write(call) and not state["decisions"][call.id]:
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": DECLINED,
                    "is_error": True,
                }
            )
            event = ToolResult(call.id, call.name, DECLINED, True, duration_ms=None, declined=True)
        else:
            result, event = await _run_tool_timed(runtime.context.tools, call)
            results.append(result)
        runtime.stream_writer(event)
    return {"messages": [{"role": "user", "content": results}], "decisions": {}}


# --- edges: pick the next node from the state ---


def after_model(state: AgentState) -> str:
    if state["stop_reason"] != "tool_use":
        return END
    if any(_is_write(call) for call in _tool_calls(state)):
        return "approve"
    return "run_tools"


def after_tools(state: AgentState, runtime: Runtime[GraphContext]) -> str:
    return "call_model" if state["steps"] < runtime.context.max_steps else END


def build_graph(checkpointer: BaseCheckpointSaver[Any]) -> CompiledStateGraph[Any, Any, Any, Any]:
    graph = StateGraph(AgentState, context_schema=GraphContext)
    graph.add_node("call_model", call_model)
    graph.add_node("approve", approve)
    graph.add_node("run_tools", run_tools)
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", after_model, ["approve", "run_tools", END])
    graph.add_edge("approve", "run_tools")
    graph.add_conditional_edges("run_tools", after_tools, ["call_model", END])
    return graph.compile(checkpointer=checkpointer)


# --- the same interface as loop.py, so the same tests run on both ---


class GraphAgent:
    """run/stream and resume, like loop.py's functions, plus a thread_id per run.

    The thread_id is the checkpoint's key: a paused run is resumed by thread_id, not by
    passing the messages back (the checkpointer already has them).
    """

    def __init__(self, checkpointer: BaseCheckpointSaver[Any] | None = None) -> None:
        # In memory: lost on restart, and not shared between processes. Fine for comparing;
        # a real deployment would need a Postgres checkpointer (see ADR-0009)
        self.graph = build_graph(checkpointer or InMemorySaver())

    async def stream(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        max_steps: int = 8,
        thread_id: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Like loop.stream_agent. Extends `messages` in place; Done(result) last.

        `messages` is the whole history, so each run needs a NEW thread_id (one is made if
        none is given): on a used thread the messages reducer would append it all again.
        Pass your own only to know which thread to resume.
        """
        if max_steps < 1:
            raise ValueError(f"max_steps should be greater than 0, got {max_steps}")
        start: AgentState = {
            "messages": list(messages),
            "steps": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "stop_reason": None,
            "decisions": {},
        }
        thread_id = thread_id or str(uuid.uuid4())
        async for event in self._run(start, claude, ctx, messages, max_steps, thread_id):
            yield event

    async def stream_resume(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        decisions: dict[str, bool],
        thread_id: str,
        max_steps: int = 8,
    ) -> AsyncIterator[AgentEvent]:
        """Like loop.stream_resume, but the paused run comes from the checkpoint.

        Decisions are checked against the paused interrupt BEFORE resuming, as in loop.py.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        snapshot = await self.graph.aget_state(config)
        if not snapshot.interrupts:
            raise ValueError(f"Thread {thread_id} isn't waiting for approval")
        write_ids = set(snapshot.interrupts[0].value["pending"])
        # Same rules as loop.stream_resume
        undecided = write_ids - decisions.keys()
        if undecided:
            raise ValueError(
                f"Every write tool call needs a decision; missing: {sorted(undecided)}"
            )
        unexpected = decisions.keys() - write_ids
        if unexpected:
            raise ValueError(f"Decisions for ids that aren't pending writes: {sorted(unexpected)}")

        # Wrapped: LangGraph reads a dict whose keys all look like interrupt ids as a map of
        # interrupt id -> value, and `{}` passes that test, so a bare `{}` resumed nothing
        resume: Command[Any] = Command(resume={"decisions": decisions})
        async for event in self._run(resume, claude, ctx, messages, max_steps, thread_id):
            yield event

    async def run(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        max_steps: int = 8,
        thread_id: str | None = None,
    ) -> AgentResult:
        return await _final(self.stream(claude, ctx, messages, max_steps, thread_id))

    async def resume(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        decisions: dict[str, bool],
        thread_id: str,
        max_steps: int = 8,
    ) -> AgentResult:
        return await _final(
            self.stream_resume(claude, ctx, messages, decisions, thread_id, max_steps)
        )

    async def _run(
        self,
        graph_input: AgentState | Command[Any],
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        max_steps: int,
        thread_id: str,
    ) -> AsyncIterator[AgentEvent]:
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        context = GraphContext(claude, ctx, max_steps)
        # "custom": only what nodes wrote with runtime.stream_writer, i.e. our events
        async for event in self.graph.astream(
            graph_input, config, context=context, stream_mode="custom"
        ):
            yield cast(AgentEvent, event)  # typed Any by LangGraph; our nodes write only these

        snapshot = await self.graph.aget_state(config)
        state = cast(AgentState, snapshot.values)
        messages[:] = state["messages"]  # the caller's list now holds the whole run
        yield Done(_result(state, paused=bool(snapshot.interrupts)))


def _tool_calls(state: AgentState) -> list[ToolUseBlock]:
    """The tool_use blocks of the last message (an assistant turn), as SDK objects."""
    content = state["messages"][-1]["content"]
    return [
        ToolUseBlock.model_validate(block)
        for block in cast(list[dict[str, Any]], content)
        if block["type"] == "tool_use"
    ]


def _result(state: AgentState, paused: bool) -> AgentResult:
    last_turn = next(m for m in reversed(state["messages"]) if m["role"] == "assistant")
    blocks = cast(list[dict[str, Any]], last_turn["content"])
    answer = "".join(block["text"] for block in blocks if block["type"] == "text")
    status: Status
    if paused:
        status = "awaiting_approval"
    elif state["stop_reason"] == "tool_use":  # ended asking for tools: only at the step limit
        status = "step_limit"
    else:
        status = _status(state["stop_reason"])
    pending = [ToolUseBlock.model_validate(b) for b in blocks if b["type"] == "tool_use"]
    return AgentResult(
        status=status,
        answer=answer,
        steps=state["steps"],
        input_tokens=state["input_tokens"],
        output_tokens=state["output_tokens"],
        pending=[call for call in pending if _is_write(call)] if paused else [],
    )


def _status(stop_reason: str | None) -> Status:
    match stop_reason:
        case "end_turn":
            return "done"
        case "max_tokens" | "refusal":
            return stop_reason
        case _:
            return "other"


async def _final(events: AsyncIterator[AgentEvent]) -> AgentResult:
    async for event in events:
        if isinstance(event, Done):
            return event.result
    raise RuntimeError("The graph stream ended without a Done event")
