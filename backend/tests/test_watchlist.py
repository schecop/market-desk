"""Adding to the watchlist baselines the company's existing filings."""

import pytest
from fakes import APPLE_CIK, NEWEST, OLDER, FakeN8n, make_edgar
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_desk.db.models import Client, SeenFiling
from market_desk.jobs.filings import check_new_filings
from market_desk.watchlist import (
    AlreadyWatchedError,
    UnknownTickerError,
    add_to_watchlist,
    list_watchlist,
    remove_from_watchlist,
)


@pytest.mark.anyio
async def test_add_stores_the_secs_ticker_cik_and_name(db_session: Session, client_id: int) -> None:
    async with make_edgar() as edgar:
        entry = await add_to_watchlist(db_session, edgar, client_id, "aapl")

    assert (entry.ticker, entry.cik, entry.name) == ("AAPL", APPLE_CIK, "Apple Inc.")
    assert [e.ticker for e in list_watchlist(db_session, client_id)] == ["AAPL"]


@pytest.mark.anyio
async def test_add_baselines_existing_filings_as_notified(
    db_session: Session, client_id: int
) -> None:
    async with make_edgar() as edgar:
        await add_to_watchlist(db_session, edgar, client_id, "AAPL")

    rows = db_session.scalars(select(SeenFiling)).all()
    assert sorted(r.accession_number for r in rows) == sorted([NEWEST, *OLDER])
    assert all(r.notified_at is not None for r in rows)  # none of them will alert


@pytest.mark.anyio
async def test_add_twice_raises(db_session: Session, client_id: int) -> None:
    async with make_edgar() as edgar:
        await add_to_watchlist(db_session, edgar, client_id, "AAPL")
        with pytest.raises(AlreadyWatchedError):
            await add_to_watchlist(db_session, edgar, client_id, "aapl")


@pytest.mark.anyio
async def test_add_unknown_ticker_raises_and_adds_nothing(
    db_session: Session, client_id: int
) -> None:
    async with make_edgar() as edgar:
        with pytest.raises(UnknownTickerError, match="ZZZZ"):
            await add_to_watchlist(db_session, edgar, client_id, "zzzz")

    assert list_watchlist(db_session, client_id) == []


@pytest.mark.anyio
async def test_remove_keeps_seen_filings_so_re_adding_does_not_alert(
    db_session: Session, client_id: int
) -> None:
    async with make_edgar() as edgar:
        await add_to_watchlist(db_session, edgar, client_id, "AAPL")

    assert remove_from_watchlist(db_session, client_id, "aapl") is True
    assert remove_from_watchlist(db_session, client_id, "AAPL") is False  # already gone
    assert list_watchlist(db_session, client_id) == []
    assert len(db_session.scalars(select(SeenFiling)).all()) == 3


@pytest.mark.anyio
async def test_add_then_check_sends_nothing(db_session: Session, client_id: int) -> None:
    """The point of the baseline: adding a company doesn't alert on its history."""
    n8n = FakeN8n()
    async with make_edgar() as edgar, n8n.dispatcher() as dispatcher:
        await add_to_watchlist(db_session, edgar, client_id, "AAPL")
        assert await check_new_filings(db_session, edgar, dispatcher) == 0

    assert n8n.events == []


@pytest.mark.anyio
async def test_each_client_has_its_own_watchlist(db_session: Session, client_id: int) -> None:
    other = Client(slug="other", name="Other client")
    db_session.add(other)
    db_session.commit()

    async with make_edgar() as edgar:
        await add_to_watchlist(db_session, edgar, client_id, "AAPL")
        await add_to_watchlist(db_session, edgar, other.id, "AAPL")  # not "already watched"

    assert remove_from_watchlist(db_session, other.id, "AAPL") is True
    assert [e.ticker for e in list_watchlist(db_session, client_id)] == ["AAPL"]
    assert list_watchlist(db_session, other.id) == []
