"""Each client's watchlist: companies whose new filings we alert on (Sprint 1 task 7).

    uv run python -m market_desk.watchlist add AAPL
    uv run python -m market_desk.watchlist remove AAPL
    uv run python -m market_desk.watchlist list
    uv run python -m market_desk.watchlist --client acme list   # default: the default client

Used by this command, the agent's tools and (Sprint 4) the dashboard.

The functions here flush but never commit: whoever opened the session owns the transaction
and decides (this command commits; the agent's caller commits once per run).
"""

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from market_desk.clients.edgar import EdgarClient, EdgarNotFoundError
from market_desk.config import get_settings
from market_desk.db.models import DEFAULT_CLIENT_SLUG, Client, SeenFiling, WatchlistEntry
from market_desk.db.session import get_sessionmaker
from market_desk.jobs.filings import WATCHED_FORM


class AlreadyWatchedError(Exception):
    """The ticker is on the watchlist already."""


class UnknownTickerError(Exception):
    """The SEC has no company with this ticker."""


async def add_to_watchlist(
    session: Session, edgar: EdgarClient, client_id: int, ticker: str
) -> WatchlistEntry:
    """Add a company and **baseline** it: its existing filings count as already notified.

    Without the baseline, the first check after adding AAPL would alert on every 10-K it ever
    filed. With it, only filings that appear after today trigger an alert.
    The caller commits.
    """
    # Translated here because only this line means "unknown ticker": a 404 from list_filings
    # below is also an EdgarNotFoundError, but the ticker exists.
    try:
        company = await edgar.get_company(ticker)
    except EdgarNotFoundError as exc:
        raise UnknownTickerError(f"The SEC has no company with ticker {ticker.upper()}") from exc
    if session.scalar(_entry(client_id, company.ticker)):
        raise AlreadyWatchedError(f"{company.ticker} is already on the watchlist")

    entry = WatchlistEntry(
        client_id=client_id, ticker=company.ticker, cik=company.cik, name=company.name
    )
    session.add(entry)

    existing = await edgar.list_filings(company.cik, form=WATCHED_FORM)
    # Another client, or another ticker with the same CIK (GOOG / GOOGL), may have baselined
    # these already: seen_filings is shared, one row per filing
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
    # Send the INSERTs now, inside the caller's transaction: a constraint violation fails here,
    # where a savepoint around this call can still undo it. Nothing is permanent until commit.
    session.flush()
    return entry


def remove_from_watchlist(session: Session, client_id: int, ticker: str) -> bool:
    """Remove a ticker; True if it was there. Its seen filings stay, so re-adding won't re-alert.

    The caller commits.
    """
    entry = session.scalar(_entry(client_id, ticker.upper()))
    if entry is None:
        return False
    session.delete(entry)
    session.flush()
    return True


def list_watchlist(session: Session, client_id: int) -> list[WatchlistEntry]:
    stmt = (
        select(WatchlistEntry)
        .where(WatchlistEntry.client_id == client_id)
        .order_by(WatchlistEntry.ticker)
    )
    return list(session.scalars(stmt))


def _entry(client_id: int, ticker: str) -> Select[WatchlistEntry]:
    """One client's row for a ticker. Every query here filters by client: no shared rows."""
    return select(WatchlistEntry).where(
        WatchlistEntry.client_id == client_id, WatchlistEntry.ticker == ticker
    )


async def _main(args: list[str]) -> None:
    usage = "usage: python -m market_desk.watchlist [--client SLUG] add|remove TICKER, or list"
    slug = DEFAULT_CLIENT_SLUG
    if args[:1] == ["--client"]:
        if len(args) < 2:
            sys.exit(usage)
        slug, args = args[1], args[2:]
    settings = get_settings()
    with get_sessionmaker()() as session:
        client = session.scalar(select(Client).where(Client.slug == slug))
        if client is None:
            sys.exit(f"No client with slug {slug!r}")
        match args:
            case ["list"]:
                for entry in list_watchlist(session, client.id):
                    print(f"{entry.ticker:<6} CIK {entry.cik:<10} {entry.name}")
            case ["add", ticker]:
                # No dev cache here: the baseline must be today's filings, not a cached list
                if settings.edgar_user_agent is None:
                    sys.exit("Set EDGAR_USER_AGENT in .env first")
                async with EdgarClient(settings.edgar_user_agent, timeout=30) as edgar:
                    entry = await add_to_watchlist(session, edgar, client.id, ticker)
                session.commit()
                print(f"Added {entry.ticker} ({entry.name}); its existing filings won't alert")
            case ["remove", ticker]:
                removed = remove_from_watchlist(session, client.id, ticker)
                session.commit()
                print(f"Removed {ticker.upper()}" if removed else f"{ticker.upper()} wasn't there")
            case _:
                sys.exit(usage)


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
