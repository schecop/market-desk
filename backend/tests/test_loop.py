"""The agent on its own: a scripted Claude, the real tools, the test database.

Every test runs twice: on the hand-written loop (loop.py) and on the LangGraph version
(graph.py). Same contract, two implementations.

No HTTP route here (test_chat.py covers that). Each test scripts Claude's replies, runs the
loop, and checks three things: what the loop returned or yielded, what it sent back to Claude
(`claude.requests`), and what ended up in the database.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol, cast

import pytest
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam
from fakes import FakeClaude, answer, claude_reply, make_edgar, tool_call
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_desk.agent.events import AgentEvent, AssistantTurn, Done, TextDelta, ToolResult
from market_desk.agent.graph import GraphAgent
from market_desk.agent.loop import (
    DECLINED,
    MODEL,
    SYSTEM_PROMPT,
    AgentResult,
    resume_agent,
    run_agent,
    stream_agent,
)
from market_desk.db.models import WatchlistEntry
from market_desk.tools import TOOLS, Tool, ToolContext


class Agent(Protocol):
    """What the tests need from an agent. The hand-written loop and the LangGraph version
    both provide it, so every test runs on both (the `agent` fixture).
    """

    def stream(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        max_steps: int = 8,
    ) -> AsyncIterator[AgentEvent]: ...

    async def run(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        max_steps: int = 8,
    ) -> AgentResult: ...

    async def resume(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        decisions: dict[str, bool],
    ) -> AgentResult: ...


class Loop:
    """loop.py: a paused run is resumed from its messages."""

    def stream(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        max_steps: int = 8,
    ) -> AsyncIterator[AgentEvent]:
        return stream_agent(claude, ctx, messages, max_steps)

    async def run(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        max_steps: int = 8,
    ) -> AgentResult:
        return await run_agent(claude, ctx, messages, max_steps)

    async def resume(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        decisions: dict[str, bool],
    ) -> AgentResult:
        return await resume_agent(claude, ctx, messages, decisions)


class Graph:
    """graph.py: a paused run is resumed from its checkpoint, so remember the last thread."""

    def __init__(self) -> None:
        self.agent = GraphAgent()
        self.thread_id = ""

    def stream(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        max_steps: int = 8,
    ) -> AsyncIterator[AgentEvent]:
        self.thread_id = str(uuid.uuid4())
        return self.agent.stream(claude, ctx, messages, max_steps, self.thread_id)

    async def run(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        max_steps: int = 8,
    ) -> AgentResult:
        self.thread_id = str(uuid.uuid4())
        return await self.agent.run(claude, ctx, messages, max_steps, self.thread_id)

    async def resume(
        self,
        claude: AsyncAnthropic,
        ctx: ToolContext,
        messages: list[MessageParam],
        decisions: dict[str, bool],
    ) -> AgentResult:
        return await self.agent.resume(claude, ctx, messages, decisions, self.thread_id)


@pytest.fixture(params=["loop", "graph"])
def agent(request: pytest.FixtureRequest) -> Agent:
    return Loop() if request.param == "loop" else Graph()


@pytest.fixture
async def ctx(db_session: Session, client_id: int) -> AsyncIterator[ToolContext]:
    """The tools' context on the fake SEC. No test here calls Cala, so it's left out."""
    async with make_edgar() as edgar:
        yield ToolContext(client_id, db_session, cast(Any, None), edgar)


def ask(question: str) -> list[MessageParam]:
    """A new conversation: one user message."""
    return [{"role": "user", "content": question}]


async def collect(events: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    """Run a stream to the end and keep every event."""
    return [event async for event in events]


def kinds(events: list[AgentEvent]) -> list[str]:
    """The events' types in order, text deltas left out (how many depends on the text)."""
    return [type(event).__name__ for event in events if not isinstance(event, TextDelta)]


def watched(db_session: Session, client_id: int) -> list[str]:
    tickers = select(WatchlistEntry.ticker).where(WatchlistEntry.client_id == client_id)
    return list(db_session.scalars(tickers))


# --- the happy path: the worked example ---


@pytest.mark.anyio
async def test_tool_call_then_answer(agent: Agent, ctx: ToolContext) -> None:
    # Arrange: Claude asks for one tool, then answers
    claude = FakeClaude([tool_call("list_watchlist", {}), answer("Your watchlist is empty.")])
    messages = ask("What's on my watchlist?")

    # Act
    events = await collect(agent.stream(claude.client(), ctx, messages))

    # Assert 1: what the loop yielded, in order, and the result in the last event
    assert kinds(events) == ["AssistantTurn", "ToolResult", "AssistantTurn", "Done"]
    done = events[-1]
    assert isinstance(done, Done)
    result = done.result
    assert result.status == "done"
    assert result.answer == "Your watchlist is empty."
    assert result.steps == 2
    assert (result.input_tokens, result.output_tokens) == (2000, 400)  # both calls, summed

    # Assert 2: what went back to Claude. The second request carries the tool's output as a
    # tool_result in a user message, matched to the call by its id.
    assert len(claude.requests) == 2
    # Every request carries the agent's setup, not just the messages (found by mutation:
    # deleting the system prompt left every test green)
    for request in claude.requests:
        assert (request["model"], request["system"]) == (MODEL, SYSTEM_PROMPT)
        assert {tool["name"] for tool in request["tools"]} == set(TOOLS)
    assert claude.requests[1]["messages"][-1] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"companies":[]}'}
        ],
    }

    # Assert 3: `messages` was extended in place: user, assistant, user (results), assistant
    assert [message["role"] for message in messages] == ["user", "assistant", "user", "assistant"]


# --- tool failures: data for Claude, not crashes ---


@pytest.mark.anyio
async def test_a_tool_error_goes_back_to_claude_and_the_loop_carries_on(
    agent: Agent, ctx: ToolContext
) -> None:
    """search_filings with a ticker the SEC doesn't know raises ToolError.

    Check: the ToolResult event has is_error=True; the second request's tool_result has
    "is_error": True and mentions the ticker; the run still ends "done" with Claude's answer.
    """
    # Arrange: Claude asks for filings of a ticker the SEC doesn't know, then answers
    claude = FakeClaude(
        [
            tool_call("search_filings", {"ticker": "ZZZZ"}),
            answer("ZZZZ is not a known ticker."),
        ]
    )
    messages = ask("Search the filings of ZZZZ")

    # Act
    events = await collect(agent.stream(claude.client(), ctx, messages))

    # Assert 1: the failure is an event like any other, flagged as an error
    assert kinds(events) == ["AssistantTurn", "ToolResult", "AssistantTurn", "Done"]
    tool_event = events[1]
    assert isinstance(tool_event, ToolResult)
    assert tool_event.is_error
    assert "ZZZZ" in tool_event.content

    # Assert 2: Claude got the error as a tool_result, so it could react to it
    result_block = claude.requests[1]["messages"][-1]["content"][0]
    assert result_block["tool_use_id"] == "toolu_1"
    assert result_block["is_error"] is True
    assert "ZZZZ" in result_block["content"]

    # Assert 3: the run didn't crash; it went on and ended with Claude's answer
    done = events[-1]
    assert isinstance(done, Done)
    assert done.result.status == "done"
    assert done.result.answer == "ZZZZ is not a known ticker."


@pytest.mark.anyio
async def test_an_unknown_tool_gets_an_error_listing_the_real_ones(
    agent: Agent, ctx: ToolContext
) -> None:
    """Claude asks for a tool that doesn't exist (say "get_stock_price").

    Check: the tool_result sent back is an error that names every tool in TOOLS.
    """
    claude = FakeClaude([tool_call("get_stock_price", {"ticker": "AAPL"}), answer("Sorry.")])

    result = await agent.run(claude.client(), ctx, ask("What's Apple's stock price?"))

    result_block = claude.requests[1]["messages"][-1]["content"][0]
    assert result_block["is_error"] is True
    assert "get_stock_price" in result_block["content"]
    for name in TOOLS:  # the error tells Claude what it can use instead
        assert name in result_block["content"]
    assert result.status == "done"


@pytest.mark.anyio
async def test_parallel_calls_get_their_results_in_one_message(
    agent: Agent, ctx: ToolContext
) -> None:
    """One reply with TWO tool_use blocks (different ids). tool_call() makes one block only:
    build the reply with claude_reply([...], "tool_use").

    Check: the second request's last message is ONE user message with two tool_results, in
    the same order as the calls, each with the right tool_use_id.
    """
    both = claude_reply(
        [
            {"type": "tool_use", "id": "toolu_a", "name": "list_watchlist", "input": {}},
            {"type": "tool_use", "id": "toolu_b", "name": "get_stock_price", "input": {}},
        ],
        "tool_use",
    )
    claude = FakeClaude([both, answer("Done.")])

    events = await collect(agent.stream(claude.client(), ctx, ask("Watchlist and price?")))

    # Each call is reported on its own...
    assert kinds(events) == ["AssistantTurn", "ToolResult", "ToolResult", "AssistantTurn", "Done"]
    # ...but both results go back in ONE user message, in the order of the calls. One failing
    # (an unknown tool) doesn't stop the other from running.
    last = claude.requests[1]["messages"][-1]
    assert last["role"] == "user"
    assert [block["tool_use_id"] for block in last["content"]] == ["toolu_a", "toolu_b"]
    assert [block.get("is_error", False) for block in last["content"]] == [False, True]


# --- the step limit ---


@pytest.mark.anyio
async def test_the_step_limit_stops_a_model_that_never_answers(
    agent: Agent, ctx: ToolContext
) -> None:
    """Claude asks for a tool every time. With max_steps=3, the loop gives up.

    Check: status "step_limit", steps 3, exactly 3 requests made (script more replies than
    that: a 4th request would be a bug the test should catch, not an IndexError).
    """
    # More replies than steps: if the loop made a 4th call, it would get a reply and the
    # request count below would catch it (instead of an IndexError from an empty script)
    claude = FakeClaude([tool_call("list_watchlist", {}, f"toolu_{n}") for n in range(5)])

    result = await agent.run(claude.client(), ctx, ask("Loop forever"), max_steps=3)

    assert result.status == "step_limit"
    assert result.steps == 3
    assert len(claude.requests) == 3
    assert (result.input_tokens, result.output_tokens) == (3000, 600)


@pytest.mark.anyio
async def test_max_steps_below_one_is_rejected_before_any_request(
    agent: Agent, ctx: ToolContext
) -> None:
    claude = FakeClaude([answer("never reached")])

    with pytest.raises(ValueError, match="max_steps"):
        await agent.run(claude.client(), ctx, ask("Hi"), max_steps=0)

    assert claude.requests == []


# --- writes wait for a human ---


@pytest.mark.anyio
async def test_a_rejected_write_is_declined_and_never_runs(
    agent: Agent, ctx: ToolContext, db_session: Session, client_id: int
) -> None:
    claude = FakeClaude(
        [tool_call("add_to_watchlist", {"ticker": "AAPL"}), answer("OK, I didn't add it.")]
    )
    messages = ask("Add Apple to my watchlist")

    paused = await agent.run(claude.client(), ctx, messages)

    # The loop stops BEFORE running the write and says which call waits
    assert paused.status == "awaiting_approval"
    assert [block.id for block in paused.pending] == ["toolu_1"]
    assert len(claude.requests) == 1
    assert watched(db_session, client_id) == []

    # A new client, like a new request: resuming needs only the messages, not the old run
    result = await agent.resume(claude.client(), ctx, messages, {"toolu_1": False})

    assert result.status == "done"
    assert claude.requests[1]["messages"][-1]["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": DECLINED, "is_error": True}
    ]
    assert watched(db_session, client_id) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("decisions", "error"),
    [
        ({}, "missing"),  # the pending call has no decision
        ({"toolu_1": True, "toolu_old": True}, "aren't pending writes"),  # an extra one
    ],
)
async def test_decisions_must_match_the_pending_writes(
    agent: Agent,
    ctx: ToolContext,
    db_session: Session,
    client_id: int,
    decisions: dict[str, bool],
    error: str,
) -> None:
    claude = FakeClaude([tool_call("add_to_watchlist", {"ticker": "AAPL"})])
    messages = ask("Add Apple to my watchlist")
    await agent.run(claude.client(), ctx, messages)
    before = list(messages)

    with pytest.raises(ValueError, match=error):
        await agent.resume(claude.client(), ctx, messages, decisions)

    # Checked before anything ran: no tool, no request, no message added
    assert watched(db_session, client_id) == []
    assert len(claude.requests) == 1
    assert messages == before


# --- a bug in a tool ---


class NoInput(BaseModel):
    pass


@pytest.mark.anyio
async def test_a_tool_bug_propagates_and_its_writes_are_undone(
    agent: Agent,
    ctx: ToolContext,
    db_session: Session,
    client_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not a ToolError: a bug. The loop doesn't hide it from the caller (the route rolls back
    and sends an `error` event), but the tool's savepoint has already undone its half-writes.
    """

    async def write_then_crash(ctx: ToolContext, params: NoInput) -> BaseModel:
        ctx.session.add(WatchlistEntry(client_id=ctx.client_id, ticker="BOOM", cik=1, name="x"))
        ctx.session.flush()  # the row is in the database (inside the savepoint) when it crashes
        raise RuntimeError("a bug in the tool")

    # A read tool (writes=False), so the loop runs it at once instead of asking for approval
    buggy = Tool(
        name="buggy", description="Crashes.", input_model=NoInput, handler=write_then_crash
    )
    monkeypatch.setitem(TOOLS, "buggy", buggy)  # put back after the test
    claude = FakeClaude([tool_call("buggy", {}), answer("never reached")])

    with pytest.raises(RuntimeError, match="a bug in the tool"):
        await agent.run(claude.client(), ctx, ask("Go"))

    assert len(claude.requests) == 1  # nothing was sent back after the crash
    assert watched(db_session, client_id) == []  # the savepoint rolled the row back


# --- how a run ends ---


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("stop_reason", "status"),
    [
        ("end_turn", "done"),
        ("max_tokens", "max_tokens"),
        ("refusal", "refusal"),
        ("stop_sequence", "other"),  # anything we don't map on purpose
    ],
)
async def test_claudes_stop_reason_becomes_the_status(
    agent: Agent, ctx: ToolContext, stop_reason: str, status: str
) -> None:
    reply = claude_reply([{"type": "text", "text": "Partial answer"}], stop_reason)
    claude = FakeClaude([reply])

    result = await agent.run(claude.client(), ctx, ask("Tell me about Apple"))

    assert result.status == status
    assert result.answer == "Partial answer"  # kept even when the run didn't end cleanly
    assert result.steps == 1


@pytest.mark.anyio
async def test_text_deltas_join_up_to_the_answer(agent: Agent, ctx: ToolContext) -> None:
    claude = FakeClaude([answer("Apple was founded in 1976.")])

    events = await collect(agent.stream(claude.client(), ctx, ask("When was Apple founded?")))

    deltas = [event.text for event in events if isinstance(event, TextDelta)]
    assert len(deltas) > 1  # really streamed, in pieces
    assert "".join(deltas) == "Apple was founded in 1976."
    turn = events[-2]
    assert isinstance(turn, AssistantTurn) and isinstance(events[-1], Done)
    assert all(not isinstance(event, ToolResult) for event in events)


# --- LangGraph only: what the checkpointer adds ---


@pytest.mark.anyio
async def test_graph_a_rejected_resume_leaves_the_run_resumable(ctx: ToolContext) -> None:
    """A bad resume must fail BEFORE it reaches the checkpoint. Checked inside the node, the
    bad value was saved as the interrupt's answer and replayed by every later resume.
    """
    graph = Graph()
    claude = FakeClaude(
        [tool_call("add_to_watchlist", {"ticker": "AAPL"}), answer("OK, I didn't add it.")]
    )
    messages = ask("Add Apple to my watchlist")
    await graph.run(claude.client(), ctx, messages)

    with pytest.raises(ValueError, match="missing"):
        await graph.resume(claude.client(), ctx, messages, {})

    result = await graph.resume(claude.client(), ctx, messages, {"toolu_1": False})
    assert result.status == "done"
