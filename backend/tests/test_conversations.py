"""Conversation tables: defaults, the CHECK constraints, cascading deletes, row locks."""

from typing import Any

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from market_desk.conversations import get_conversation
from market_desk.db.models import Conversation, Message, ToolCall

TOOL_USE = {"type": "tool_use", "id": "toolu_01", "name": "list_watchlist", "input": {}}


def conversation_with_a_tool_call(session: Session, client_id: int) -> Conversation:
    conversation = Conversation(client_id=client_id)
    session.add(conversation)
    session.flush()  # assigns ids, so the children can point at their parents
    message = Message(conversation_id=conversation.id, role="assistant", content=[TOOL_USE])
    session.add(message)
    session.flush()
    session.add(
        ToolCall(
            message_id=message.id,
            tool_use_id="toolu_01",
            name="list_watchlist",
            input={},
            status="done",
        )
    )
    session.commit()
    return conversation


def count(session: Session, model: type[Message] | type[ToolCall]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_ids_and_defaults_are_filled_in(db_session: Session, client_id: int) -> None:
    conversation = conversation_with_a_tool_call(db_session, client_id)

    assert conversation.id.version == 4  # a random UUID, made in Python
    call = db_session.scalars(select(ToolCall)).one()
    assert call.is_error is False
    message = db_session.scalars(select(Message)).one()
    assert message.content == [TOOL_USE]  # JSONB gives back the same structure


def test_role_outside_the_check_constraint_is_rejected(db_session: Session, client_id: int) -> None:
    conversation = Conversation(client_id=client_id)
    db_session.add(conversation)
    db_session.flush()
    db_session.add(Message(conversation_id=conversation.id, role="system", content=[]))

    with pytest.raises(IntegrityError, match="ck_messages_role"):
        db_session.flush()


def test_deleting_a_conversation_deletes_its_messages_and_tool_calls(
    db_session: Session, client_id: int
) -> None:
    conversation = conversation_with_a_tool_call(db_session, client_id)

    db_session.delete(conversation)
    db_session.commit()

    # ON DELETE CASCADE runs in Postgres, not in SQLAlchemy: the rows are gone in the database
    assert count(db_session, Message) == 0
    assert count(db_session, ToolCall) == 0


def test_get_conversation_locks_the_row_only_when_asked(
    db_session: Session, client_id: int
) -> None:
    conversation = conversation_with_a_tool_call(db_session, client_id)
    sent: list[str] = []

    # Record each SQL statement as it's sent to Postgres, on this test's connection only
    def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        sent.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        get_conversation(db_session, client_id, conversation.id)
        get_conversation(db_session, client_id, conversation.id, lock=True)
    finally:
        event.remove(connection, "before_cursor_execute", record)

    plain, locked = sent
    assert "FOR UPDATE" not in plain
    assert locked.rstrip().endswith("FOR UPDATE")
