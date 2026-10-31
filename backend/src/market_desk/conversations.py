"""Conversations in Postgres: load the history the loop needs, save what a run added.

Like watchlist.py, these functions flush and never commit: the caller (the /chat route) owns
the unit of work and commits once, when the run has finished.
"""

import uuid
from collections.abc import Iterable
from typing import Any, cast

from anthropic.types import MessageParam
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_desk.agent.events import AgentEvent, AssistantTurn, ToolResult
from market_desk.db.models import Conversation, Message, ToolCall


def create_conversation(session: Session, client_id: int, title: str) -> Conversation:
    conversation = Conversation(client_id=client_id, title=title[:200])
    session.add(conversation)
    session.flush()  # the UUID default is applied on flush; the route needs the id now
    return conversation


def get_conversation(
    session: Session, client_id: int, conversation_id: uuid.UUID, *, lock: bool = False
) -> Conversation | None:
    """The conversation, only if it belongs to this client.

    Another client's id gives None, the same as an id that doesn't exist: the caller answers
    404 for both, so nobody can probe which conversation ids exist.

    With `lock`, the row is locked (SELECT ... FOR UPDATE) until the session commits or rolls
    back: a second request for the same conversation waits here, then sees what the first one
    saved. Without it, two approvals could both see the call pending and both run it.
    """
    query = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.client_id == client_id
    )
    if lock:
        query = query.with_for_update()
    return session.scalars(query).one_or_none()


def load_messages(session: Session, conversation_id: uuid.UUID) -> list[MessageParam]:
    """The history in the Claude API's format, oldest first. Blocks come back as plain dicts."""
    rows = session.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    )
    # role is a str column; the CHECK constraint guarantees it's "user" or "assistant"
    return [cast(MessageParam, {"role": row.role, "content": row.content}) for row in rows]


def has_pending_approval(session: Session, conversation_id: uuid.UUID) -> bool:
    """True while the last turn's tool calls wait for a human decision."""
    pending = session.scalars(
        select(ToolCall.id)
        .join(Message, ToolCall.message_id == Message.id)
        .where(Message.conversation_id == conversation_id, ToolCall.status == "pending_approval")
        .limit(1)
    ).first()
    return pending is not None


def save_run(
    session: Session,
    conversation_id: uuid.UUID,
    new_messages: list[MessageParam],
    events: list[AgentEvent],
) -> None:
    """Store the messages a run added, and one tool_calls row per tool call.

    `events` are the run's events in order: each AssistantTurn carries the token counts of one
    new assistant message, and each ToolResult says how a call ended.
    """
    turns = iter([event for event in events if isinstance(event, AssistantTurn)])

    for message in new_messages:
        content = _to_json(message["content"])
        row = Message(conversation_id=conversation_id, role=message["role"], content=content)
        if message["role"] == "assistant":
            # Assistant messages and AssistantTurn events are made together, one each per step
            turn = next(turns)
            row.input_tokens = turn.input_tokens
            row.output_tokens = turn.output_tokens
        session.add(row)
        session.flush()  # assigns row.id for the tool_calls rows below

        for block in content:
            if block["type"] == "tool_use":
                # Every call starts as pending; the results below (now or after an approval,
                # in a later run) move it on. If the turn waits for a human, all its calls
                # wait, reads included: none of them has run yet.
                session.add(
                    ToolCall(
                        message_id=row.id,
                        tool_use_id=block["id"],
                        name=block["name"],
                        input=block["input"],
                        status="pending_approval",
                    )
                )
    session.flush()

    for event in events:
        if isinstance(event, ToolResult):
            # On a resume, the call's row was created by the earlier run: found by its API id
            call = session.scalars(
                select(ToolCall).where(ToolCall.tool_use_id == event.tool_use_id)
            ).one()
            call.output = event.content
            call.is_error = event.is_error
            call.duration_ms = event.duration_ms
            if event.declined:
                call.status = "rejected"
            else:
                call.status = "error" if event.is_error else "done"
    session.flush()


def _to_json(content: str | Iterable[Any]) -> list[dict[str, Any]]:
    """Content as JSON-ready content blocks, whatever shape the loop left it in.

    A user message can be a plain string; assistant content is SDK objects (Pydantic models);
    tool results and reloaded history are already dicts.
    """
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    # exclude_none: the SDK's optional fields (a text block's citations...) are None when
    # unused; leaving them out stores exactly what the API would accept back
    return [
        block.model_dump(mode="json", exclude_none=True)
        if isinstance(block, BaseModel)
        else cast(dict[str, Any], block)  # already a dict: a tool_result or reloaded history
        for block in content
    ]
