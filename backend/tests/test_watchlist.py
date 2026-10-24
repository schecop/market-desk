"""Adding to the watchlist baselines the company's existing filings."""

import pytest
from fakes import APPLE_CIK, NEWEST, OLDER, FakeN8n, make_edgar
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_desk.db.models import SeenFiling
from market_desk.jobs.filings import check_new_filings
from market_desk.watchlist import (
    AlreadyWatchedError,
    UnknownTickerError,
    add_to_watchlist,
    list_watchlist,
    remove_from_watchlist,
)


@pytest.mark.anyio
async def test_add_stores_the_secs_ticker_cik_and_name(db_session: Session) -> None:
    async with make_edgar() as edgar:
        entry = await add_to_watchlist(db_session, edgar, "aapl")

    assert (entry.ticker, entry.cik, entry.name) == ("AAPL", APPLE_CIK, "Apple Inc.")
    assert [e.ticker for e in list_watchlist(db_session)] == ["AAPL"]


@pytest.mark.anyio
async def test_add_baselines_existing_filings_as_notified(db_session: Session) -> None:
    async with make_edgar() as edgar:
        await add_to_watchlist(db_session, edgar, "AAPL")

    rows = db_session.scalars(select(SeenFiling)).all()
    assert sorted(r.accession_number for r in rows) == sorted([NEWEST, *OLDER])
    assert all(r.notified_at is not None for r in rows)  # none of them will alert


@pytest.mark.anyio
async def test_add_twice_raises(db_session: Session) -> None:
    async with make_edgar() as edgar:
        await add_to_watchlist(db_session, edgar, "AAPL")
        with pytest.raises(AlreadyWatchedError):
            await add_to_watchlist(db_session, edgar, "aapl")


@pytest.mark.anyio
async def test_add_unknown_ticker_raises_and_adds_nothing(db_session: Session) -> None:
    async with make_edgar() as edgar:
        with pytest.raises(UnknownTickerError, match="ZZZZ"):
            await add_to_watchlist(db_session, edgar, "zzzz")

    assert list_watchlist(db_session) == []


@pytest.mark.anyio
async def test_remove_keeps_seen_filings_so_re_adding_does_not_alert(db_session: Session) -> None:
    async with make_edgar() as edgar:
        await add_to_watchlist(db_session, edgar, "AAPL")

    assert remove_from_watchlist(db_session, "aapl") is True
    assert remove_from_watchlist(db_session, "AAPL") is False  # already gone
    assert list_watchlist(db_session) == []
    assert len(db_session.scalars(select(SeenFiling)).all()) == 3


@pytest.mark.anyio
async def test_add_then_check_sends_nothing(db_session: Session) -> None:
    """The point of the baseline: adding a company doesn't alert on its history."""
    n8n = FakeN8n()
    async with make_edgar() as edgar, n8n.dispatcher() as dispatcher:
        await add_to_watchlist(db_session, edgar, "AAPL")
        assert await check_new_filings(db_session, edgar, dispatcher) == 0

    assert n8n.events == []
