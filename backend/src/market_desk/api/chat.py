"""POST /chat: run the agent and stream what it does as Server-Sent Events (SSE).

    POST /chat                               {"message": "...", "conversation_id": null}
    POST /chat/{conversation_id}/approvals   {"decisions": {"toolu_...": true}}

Everything that can fail cleanly (unknown client, conversation, a pending approval) is checked
BEFORE the stream starts, so it gets a real status code. Once the first byte is sent the
status is 200 for good: a failure after that can only be reported as an `error` event.

A whole request is one unit of work: the run's messages, tool calls and tool writes are
committed together when it ends, or all rolled back if anything fails on the way.
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any

from anthropic.types import MessageParam
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_desk.agent.events import AgentEvent, AssistantTurn, Done, ToolResult
from market_desk.agent.loop import stream_agent, stream_resume
from market_desk.agent.services import AgentServices
from market_desk.conversations import (
    create_conversation,
    get_conversation,
    has_pending_approval,
    load_messages,
    save_run,
)
from market_desk.db.models import Client, Conversation
from market_desk.db.session import get_sessionmaker
from market_desk.tools import ToolContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Headers for a stream: don't cache it, and ask proxies (nginx, load balancers) not to buffer
# it, or the events arrive all at once at the end
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    conversation_id: uuid.UUID | None = None  # None starts a new conversation


class ApprovalRequest(BaseModel):
    # tool_use_id -> approved? Every pending write call of the last turn needs one
    decisions: dict[str, bool] = Field(min_length=1)


def get_agent_services(request: Request) -> AgentServices:
    """The clients the lifespan built (api/main.py). Tests override this dependency."""
    services: AgentServices | None = getattr(request.app.state, "agent", None)
    if services is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The agent isn't configured: set ANTHROPIC_API_KEY, CALA_API_KEY and EDGAR_USER_AGENT",
        )
    return services


Services = Annotated[AgentServices, Depends(get_agent_services)]
# The factory, not a session: the stream outlives the route function. The route opens the
# session and hands it to the stream, which closes it at the end (see _stream).
SessionFactory = Annotated[Callable[[], Session], Depends(get_sessionmaker)]
# Which client is asking. A stand-in until per-client API keys (Sprint 4): the header's
# client is trusted as is. Read as `X-Client` (FastAPI turns x_client into that header).
ClientSlug = Annotated[str, Header()]


@router.post("")
async def chat(
    body: ChatRequest,
    services: Services,
    session_factory: SessionFactory,
    x_client: ClientSlug = "default",
) -> StreamingResponse:
    session = session_factory()
    try:
        client_id = _client_id(session, x_client)
        if body.conversation_id is None:
            conversation = create_conversation(session, client_id, title=body.message)
            messages: list[MessageParam] = []
        else:
            conversation = _conversation(session, client_id, body.conversation_id)
            if has_pending_approval(session, conversation.id):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "This conversation is waiting for approval: decide the pending calls first",
                )
            messages = load_messages(session, conversation.id)
    except BaseException:
        session.close()  # the stream never starts, so it won't close the session
        raise

    start = len(messages)  # everything from here on is new and gets saved
    messages.append({"role": "user", "content": body.message})
    ctx = ToolContext(client_id, session, services.cala, services.edgar)
    events = stream_agent(services.anthropic, ctx, messages)
    return _response(session, conversation, events, messages, start)


@router.post("/{conversation_id}/approvals")
async def approve(
    conversation_id: uuid.UUID,
    body: ApprovalRequest,
    services: Services,
    session_factory: SessionFactory,
    x_client: ClientSlug = "default",
) -> StreamingResponse:
    session = session_factory()
    try:
        client_id = _client_id(session, x_client)
        conversation = _conversation(session, client_id, conversation_id)
        if not has_pending_approval(session, conversation.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for approval")
        messages = load_messages(session, conversation.id)
    except BaseException:
        session.close()
        raise

    start = len(messages)
    ctx = ToolContext(client_id, session, services.cala, services.edgar)
    # Whether the decisions match the pending calls is checked by stream_resume itself, once
    # the stream has started: a mismatch arrives as an `error` event, not a 400
    events = stream_resume(services.anthropic, ctx, messages, body.decisions)
    return _response(session, conversation, events, messages, start)


def _client_id(session: Session, slug: str) -> int:
    client_id = session.scalars(select(Client.id).where(Client.slug == slug)).one_or_none()
    if client_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown client: {slug}")
    return client_id


def _conversation(session: Session, client_id: int, conversation_id: uuid.UUID) -> Conversation:
    conversation = get_conversation(session, client_id, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


def _response(
    session: Session,
    conversation: Conversation,
    events: AsyncIterator[AgentEvent],
    messages: list[MessageParam],
    start: int,
) -> StreamingResponse:
    return StreamingResponse(
        _stream(session, conversation.id, events, messages, start),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def _stream(
    session: Session,
    conversation_id: uuid.UUID,
    events: AsyncIterator[AgentEvent],
    messages: list[MessageParam],
    start: int,
) -> AsyncIterator[str]:
    """Pass the loop's events on as SSE, then save the run and commit. Owns the session.

    Starlette runs this generator after the route function has returned, so the session can't
    come from a `Depends` that closes when the route is done: the stream closes it itself.
    """
    seen: list[AgentEvent] = []
    try:
        yield _sse("conversation", {"conversation_id": str(conversation_id)})
        async for event in events:
            seen.append(event)
            if isinstance(event, Done):
                # Save BEFORE announcing done: a client that sees `done` can trust it's stored
                save_run(session, conversation_id, messages[start:], seen)
                session.commit()
            for name, data in _to_sse(event):
                yield _sse(name, data)
    except Exception:
        # Broad on purpose: whatever failed (a bug, Claude down, a decision mismatch), undo the
        # whole run, so the history never holds a tool_use without its tool_result
        session.rollback()
        logger.exception("Chat run failed in conversation %s", conversation_id)
        yield _sse("error", {"message": "The run failed and nothing was saved. Try again."})
    finally:
        session.close()


def _to_sse(event: AgentEvent) -> list[tuple[str, dict[str, Any]]]:
    """An event as (SSE event name, JSON data) pairs: what the browser needs, nothing more."""
    match event:
        case AssistantTurn(content=content):
            pairs: list[tuple[str, dict[str, Any]]] = []
            for block in content:
                if block.type == "text":
                    pairs.append(("text", {"text": block.text}))
                elif block.type == "tool_use":
                    pairs.append(
                        ("tool_use", {"id": block.id, "name": block.name, "input": block.input})
                    )
                # thinking blocks stay server-side
            return pairs
        case ToolResult():
            data = {
                "tool_use_id": event.tool_use_id,
                "name": event.name,
                "content": event.content,
                "is_error": event.is_error,
                "declined": event.declined,
                "duration_ms": event.duration_ms,
            }
            return [("tool_result", data)]
        case Done(result=result):
            cost = result.input_tokens_usd + result.output_tokens_usd
            data = {
                "status": result.status,
                "answer": result.answer,
                "steps": result.steps,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": round(cost, 6),
                "pending": [{"id": b.id, "name": b.name, "input": b.input} for b in result.pending],
            }
            return [("done", data)]


def _sse(name: str, data: dict[str, Any]) -> str:
    """One SSE message: `event:` and `data:` lines, ended by a blank line.

    json.dumps escapes newlines inside strings, so the data always fits on its one line.
    """
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"
