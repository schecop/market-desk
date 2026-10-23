"""Table models. Alembic's env.py imports this module so autogenerate sees every table."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from market_desk.db.base import Base


class WatchlistEntry(Base):
    """A company whose new filings we alert on. One row per ticker (Sprint 2 adds the client)."""

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), unique=True)
    # Not unique: two tickers can share a CIK (GOOG and GOOGL are both Alphabet)
    cik: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(200))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SeenFiling(Base):
    """A filing we've found on EDGAR. The outbox for alerts: notified_at is NULL until delivered.

    Linked to the watchlist by CIK, not a foreign key, because CIK isn't unique there.
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
