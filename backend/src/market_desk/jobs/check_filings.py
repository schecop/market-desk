"""Run the filing check: once from the command line, or on a timer inside the API.

    uv run python -m market_desk.jobs.check_filings      # one run, then exit

The API starts `filing_check_loop` when FILING_CHECK_INTERVAL_MINUTES > 0 (api/main.py).
"""

import asyncio
import logging
import sys

from market_desk.clients.edgar import EdgarClient
from market_desk.config import Settings, get_settings
from market_desk.db.session import get_sessionmaker
from market_desk.jobs.filings import check_new_filings
from market_desk.webhooks.outbound import WebhookDispatcher

logger = logging.getLogger(__name__)


class NotConfiguredError(Exception):
    """A setting the check needs is missing."""


async def run_check_once(settings: Settings) -> int:
    """One check with real clients; returns how many events were delivered."""
    if settings.edgar_user_agent is None:
        raise NotConfiguredError("Set EDGAR_USER_AGENT")
    if settings.n8n_webhook_url is None or settings.webhook_signing_secret is None:
        raise NotConfiguredError("Set N8N_WEBHOOK_URL and WEBHOOK_SIGNING_SECRET")

    # Built directly, not with from_settings: the dev cache would hide new filings
    edgar = EdgarClient(settings.edgar_user_agent, timeout=30)
    dispatcher = WebhookDispatcher(
        settings.n8n_webhook_url, settings.webhook_signing_secret.get_secret_value()
    )
    # Sync session in async code: these queries take milliseconds, so blocking is acceptable
    # at this scale. Many companies or a busy API would call for SQLAlchemy's async engine.
    with get_sessionmaker()() as session:
        async with edgar, dispatcher:
            return await check_new_filings(session, edgar, dispatcher)


async def filing_check_loop(interval_minutes: float) -> None:
    """Check, sleep, repeat, until cancelled. A failed run is logged, never fatal."""
    logger.info("Filing check every %s minutes", interval_minutes)
    while True:
        try:
            delivered = await run_check_once(get_settings())
            logger.info("Filing check done: %d new filing(s) announced", delivered)
        except Exception:
            # Broad on purpose: one bad run (EDGAR down, a bug) must not kill the timer
            logger.exception("Filing check failed; trying again in %s minutes", interval_minutes)
        await asyncio.sleep(interval_minutes * 60)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        delivered = asyncio.run(run_check_once(get_settings()))
    except NotConfiguredError as err:
        sys.exit(f"{err} in .env first")
    print(f"{delivered} new filing(s) announced")


if __name__ == "__main__":
    main()
