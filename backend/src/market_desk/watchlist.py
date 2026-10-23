"""The watchlist: companies whose new filings we alert on (task 7).

    uv run python -m market_desk.watchlist add AAPL
    uv run python -m market_desk.watchlist remove AAPL
    uv run python -m market_desk.watchlist list

A command for now; the agent's tools (Sprint 2) and the dashboard (Sprint 4) come later.
"""

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_desk.clients.edgar import EdgarClient
from market_desk.config import get_settings
from market_desk.db.models import SeenFiling, WatchlistEntry
from market_desk.db.session import get_sessionmaker
from market_desk.jobs.filings import WATCHED_FORM


class AlreadyWatchedError(Exception):
    """The ticker is on the watchlist already."""


async def add_to_watchlist(session: Session, edgar: EdgarClient, ticker: str) -> WatchlistEntry:
    """Add a company and **baseline** it: its existing filings count as already notified.

    Without the baseline, the first check after adding AAPL would alert on every 10-K it ever
    filed. With it, only filings that appear after today trigger an alert.
    """
    company = await edgar.get_company(ticker)  # EdgarNotFoundError for an unknown ticker
    if session.scalar(select(WatchlistEntry).where(WatchlistEntry.ticker == company.ticker)):
        raise AlreadyWatchedError(f"{company.ticker} is already on the watchlist")

    entry = WatchlistEntry(ticker=company.ticker, cik=company.cik, name=company.name)
    session.add(entry)

    existing = await edgar.list_filings(company.cik, form=WATCHED_FORM)
    # Another ticker with the same CIK (GOOG / GOOGL) may have baselined these already
    known = set(
        session.scalars(
            select(SeenFiling.accession_number).where(SeenFiling.cik == company.cik)
        ).all()
    )
    now = datetime.now(UTC)
    for filing in existing:
        if filing.accession_number not in known:
            session.add(
                SeenFiling(
                    accession_number=filing.accession_number,
                    cik=company.cik,
                    form=filing.form,
                    filing_date=filing.filing_date,
                    primary_document=filing.primary_document,
                    notified_at=now,  # baseline: seen and "notified", so never alerted
                )
            )
    session.commit()
    return entry


def remove_from_watchlist(session: Session, ticker: str) -> bool:
    """Remove a ticker; True if it was there. Its seen filings stay, so re-adding won't re-alert."""
    entry = session.scalar(select(WatchlistEntry).where(WatchlistEntry.ticker == ticker.upper()))
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True


def list_watchlist(session: Session) -> list[WatchlistEntry]:
    return list(session.scalars(select(WatchlistEntry).order_by(WatchlistEntry.ticker)))


async def _main(args: list[str]) -> None:
    usage = "usage: python -m market_desk.watchlist add|remove TICKER, or list"
    settings = get_settings()
    with get_sessionmaker()() as session:
        match args:
            case ["list"]:
                for entry in list_watchlist(session):
                    print(f"{entry.ticker:<6} CIK {entry.cik:<10} {entry.name}")
            case ["add", ticker]:
                # No dev cache here: the baseline must be today's filings, not a cached list
                if settings.edgar_user_agent is None:
                    sys.exit("Set EDGAR_USER_AGENT in .env first")
                async with EdgarClient(settings.edgar_user_agent, timeout=30) as edgar:
                    entry = await add_to_watchlist(session, edgar, ticker)
                print(f"Added {entry.ticker} ({entry.name}); its existing filings won't alert")
            case ["remove", ticker]:
                removed = remove_from_watchlist(session, ticker)
                print(f"Removed {ticker.upper()}" if removed else f"{ticker.upper()} wasn't there")
            case _:
                sys.exit(usage)


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
