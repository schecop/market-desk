"""Conversation tables: defaults, the CHECK constraints, and cascading deletes."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
