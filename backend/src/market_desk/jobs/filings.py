"""Detect new filings for watchlist companies and announce them (Sprint 1 task 7).

The outbox pattern: a new filing is first recorded in seen_filings with notified_at NULL, then
sent; notified_at is set only once the receiver answered 2xx. Anything still NULL is retried on
the next check, so a delivery can repeat but is never lost (at-least-once). Each event's id is
derived from the accession number, so a repeat carries the same id and receivers can dedupe it.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_desk.clients.edgar import ARCHIVES_URL, EdgarClient, EdgarError
from market_desk.db.models import SeenFiling, WatchlistEntry
from market_desk.webhooks.events import WebhookEvent
from market_desk.webhooks.outbound import WebhookDeliveryError, WebhookDispatcher

logger = logging.getLogger(__name__)

WATCHED_FORM = "10-K"


def filing_event_id(accession_number: str) -> str:
    """Same filing, same event id, on every attempt and every check run."""
    return f"msg_{accession_number}"


async def check_new_filings(
    session: Session, edgar: EdgarClient, dispatcher: WebhookDispatcher
) -> int:
    """Record new WATCHED_FORM filings of watchlist companies and send one event each.

    Returns how many events were delivered in this run.

    1. For each distinct CIK on the watchlist: `edgar.list_filings(cik, form=WATCHED_FORM)`,
       and insert the accession numbers not yet in seen_filings (notified_at=None). Commit.
       An EdgarError for one company is logged and skipped: the others still get checked.
    2. For each SeenFiling with notified_at IS NULL (new now, or left over from a failed run):
       send a `filing.created` WebhookEvent with id=filing_event_id(...) and `data` shaped like
       SAMPLE_FILING in webhooks/send_test.py (ticker and company name from the watchlist row
       with that CIK; url from ARCHIVES_URL in clients/edgar.py). On success, set notified_at to
       now (UTC) and commit; on WebhookDeliveryError, log it and leave it for the next run.
    """
    new_filings = 0

    stmt1 = select(WatchlistEntry.cik).distinct()
    ciks = session.scalars(stmt1).all()
    for cik in ciks:
        try:
            filings = await edgar.list_filings(cik, WATCHED_FORM)
        except EdgarError as err:
            logger.warning("Skipping CIK %s this run: %s", cik, err)
            continue
        stmt2 = select(SeenFiling.accession_number).where(SeenFiling.cik == cik)
        accession_numbers = set(session.scalars(stmt2).all())
        for filing in filings:
            if filing.accession_number not in accession_numbers:
                obj = SeenFiling(
                    accession_number=filing.accession_number,
                    cik=cik,
                    form=filing.form,
                    filing_date=filing.filing_date,
                    primary_document=filing.primary_document,
                    notified_at=None,
                )
                session.add(obj)
        session.commit()

    stmt3 = select(SeenFiling).where(SeenFiling.notified_at.is_(None))
    pending_filings = session.scalars(stmt3).all()
    for pending_filing in pending_filings:
        watchlist_entry = session.scalar(
            select(WatchlistEntry)
            .where(WatchlistEntry.cik == pending_filing.cik)
            .order_by(WatchlistEntry.ticker)
        )
        if watchlist_entry is None:
            # Removed from the watchlist while this filing was pending: leave it unsent
            logger.info(
                "CIK %s is no longer watched; not announcing %s",
                pending_filing.cik,
                pending_filing.accession_number,
            )
            continue
        event = WebhookEvent(
            id=filing_event_id(pending_filing.accession_number),
            type="filing.created",
            data={
                "ticker": watchlist_entry.ticker,
                "company": watchlist_entry.name,
                "cik": pending_filing.cik,
                "form": pending_filing.form,
                "filing_date": pending_filing.filing_date,
                "accession_number": pending_filing.accession_number,
                "url": ARCHIVES_URL.format(
                    cik=pending_filing.cik,
                    accession=pending_filing.accession_number.replace("-", ""),
                    document=pending_filing.primary_document,
                ),
            },
        )
        try:
            await dispatcher.send(event)
        except WebhookDeliveryError as err:
            logger.warning("Couldn't deliver %s, retrying next run: %s", event.id, err)
            continue

        pending_filing.notified_at = datetime.now(UTC)
        session.commit()
        new_filings += 1

    return new_filings
