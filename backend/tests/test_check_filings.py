"""check_new_filings against a fake SEC, a fake n8n (tests/fakes.py) and the test database.

Apple has three 10-Ks; most tests baseline the OLDER two, so NEWEST is the "new" filing.
"""

from datetime import UTC, date, datetime

import pytest
from fakes import APPLE_CIK, NEWEST, OLDER, FakeN8n, make_edgar
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_desk.db.models import SeenFiling, WatchlistEntry
from market_desk.jobs.filings import check_new_filings


@pytest.fixture
def n8n() -> FakeN8n:
    return FakeN8n()


async def run_check(session: Session, n8n: FakeN8n) -> int:
    async with make_edgar() as edgar, n8n.dispatcher() as dispatcher:
        return await check_new_filings(session, edgar, dispatcher)


def watch(session: Session, ticker: str, cik: int, name: str, baseline: list[str]) -> None:
    """A watchlist row plus already-notified filings, as add_to_watchlist would leave them."""
    session.add(WatchlistEntry(ticker=ticker, cik=cik, name=name))
    for accession in baseline:
        session.add(
            SeenFiling(
                accession_number=accession,
                cik=cik,
                form="10-K",
                filing_date=date(2024, 1, 1),
                primary_document="old.htm",
                notified_at=datetime.now(UTC),
            )
        )
    session.commit()


def seen(session: Session, accession: str) -> SeenFiling:
    return session.scalars(select(SeenFiling).where(SeenFiling.accession_number == accession)).one()


@pytest.mark.anyio
async def test_new_filing_is_sent_and_marked_notified(db_session: Session, n8n: FakeN8n) -> None:
    watch(db_session, "AAPL", APPLE_CIK, "Apple Inc.", baseline=OLDER)

    delivered = await run_check(db_session, n8n)

    assert delivered == 1
    [event] = n8n.events
    assert event["id"] == f"msg_{NEWEST}"
    assert event["type"] == "filing.created"
    assert event["data"] == {
        "ticker": "AAPL",
        "company": "Apple Inc.",
        "cik": APPLE_CIK,
        "form": "10-K",
        "filing_date": "2025-10-31",
        "accession_number": NEWEST,
        "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
    }
    assert seen(db_session, NEWEST).notified_at is not None


@pytest.mark.anyio
async def test_nothing_new_sends_nothing(db_session: Session, n8n: FakeN8n) -> None:
    watch(db_session, "AAPL", APPLE_CIK, "Apple Inc.", baseline=[NEWEST, *OLDER])

    assert await run_check(db_session, n8n) == 0
    assert n8n.events == []


@pytest.mark.anyio
async def test_failed_delivery_is_kept_and_retried_next_run_with_the_same_id(
    db_session: Session, n8n: FakeN8n
) -> None:
    watch(db_session, "AAPL", APPLE_CIK, "Apple Inc.", baseline=OLDER)
    n8n.status = 500  # n8n is down for the whole first run

    assert await run_check(db_session, n8n) == 0
    assert seen(db_session, NEWEST).notified_at is None  # recorded, not lost

    n8n.status = 202  # back up
    assert await run_check(db_session, n8n) == 1
    assert seen(db_session, NEWEST).notified_at is not None
    # Every attempt, in both runs, carried the same id: receivers can dedupe
    assert {e["id"] for e in n8n.events} == {f"msg_{NEWEST}"}


@pytest.mark.anyio
async def test_an_edgar_error_for_one_company_does_not_stop_the_others(
    db_session: Session, n8n: FakeN8n
) -> None:
    watch(db_session, "MSFT", 789019, "MICROSOFT CORP", baseline=[])  # no fixture: the SEC 404s
    watch(db_session, "AAPL", APPLE_CIK, "Apple Inc.", baseline=OLDER)

    assert await run_check(db_session, n8n) == 1
    assert [e["data"]["ticker"] for e in n8n.events] == ["AAPL"]


@pytest.mark.anyio
async def test_two_tickers_with_one_cik_send_one_event_per_filing(
    db_session: Session, n8n: FakeN8n
) -> None:
    # Like GOOG and GOOGL: two share classes, one company, one set of filings
    watch(db_session, "AAPL", APPLE_CIK, "Apple Inc.", baseline=OLDER)
    watch(db_session, "AAPL.B", APPLE_CIK, "Apple Inc.", baseline=[])

    assert await run_check(db_session, n8n) == 1
    assert [e["id"] for e in n8n.events] == [f"msg_{NEWEST}"]
