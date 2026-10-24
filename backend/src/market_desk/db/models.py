"""Table models. Alembic's env.py imports this module so autogenerate sees every table."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from market_desk.db.base import Base

# Created by the migration that introduced clients; existing watchlist rows were moved to it
DEFAULT_CLIENT_SLUG = "default"


class Client(Base):
    """A customer of Market Desk. Owns a watchlist and conversations; config comes in Sprint 4."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable, human-readable handle for CLIs, URLs and config ("default", "acme")
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchlistEntry(Base):
    """A company a client watches; we alert on its new filings. One row per (client, ticker)."""

    __tablename__ = "watchlists"
    # The unique index also serves "this client's watchlist" lookups: client_id is its first column
    __table_args__ = (UniqueConstraint("client_id", "ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT: a client can't be deleted while it still watches companies
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"))
    ticker: Mapped[str] = mapped_column(String(10))
    # Not unique: two tickers can share a CIK (GOOG and GOOGL are both Alphabet)
    cik: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(200))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SeenFiling(Base):
    """A filing we've found on EDGAR. The outbox for alerts: notified_at is NULL until delivered.

    Linked to watchlists by CIK, not a foreign key: one filing serves every client watching that
    company, and CIK isn't unique there.
    """

    __tablename__ = "seen_filings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # EDGAR's id for a filing; unique, so finding the same filing twice can't insert it twice
    accession_number: Mapped[str] = mapped_column(String(25), unique=True)
    cik: Mapped[int] = mapped_column(Integer, index=True)
    form: Mapped[str] = mapped_column(String(20))
    filing_date: Mapped[date] = mapped_column(Date)
    primary_document: Mapped[str] = mapped_column(String(200))  # builds the document URL
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # NULL = found but not delivered yet; the next check retries it (at-least-once delivery)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(Base):
    """One chat between a client's user and the agent.

    The id is a UUID because it appears in API URLs: sequential ids would let anyone guess
    another client's conversations. Messages and tool calls are only reached through it.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    """One message in the Claude API's format: `content` keeps the raw content blocks (text,
    tool_use, tool_result) so the conversation can be sent back to the model as it was.

    Token counts are set on assistant messages only; they're the basis for cost per run.
    """

    __tablename__ = "messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    input_tokens: Mapped[int | None] = mapped_column()
    output_tokens: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolCall(Base):
    """A tool the agent ran (or wants to run), recorded for auditing and confirmation.

    Duplicates the tool_use block in `messages` on purpose: that block is what the model saw,
    this row is what we executed, queryable without digging through JSON ("which tools fail?",
    "what is waiting for approval?"). Write tools start as pending_approval (task 4).
    """

    __tablename__ = "tool_calls"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'done', 'error')", name="status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    # The API's id ("toolu_..."): links the call to its tool_result; unique, so it's recorded once
    tool_use_id: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(64))  # the Claude API's limit for tool names
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output: Mapped[str | None] = mapped_column(Text)  # a tool result can be several KB
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
