"""Send one sample event to N8N_WEBHOOK_URL, to check the n8n flow end to end (task 6).

    uv run python -m market_desk.webhooks.send_test              # a sample filing.created
    uv run python -m market_desk.webhooks.send_test test.ping    # a no-op event

The real filing.created events come from the scheduled check (task 7); this one is made up.
"""

import asyncio
import sys
from typing import get_args

from market_desk.config import get_settings
from market_desk.webhooks.events import EventType, WebhookEvent
from market_desk.webhooks.outbound import WebhookDeliveryError, WebhookDispatcher

# The shape of a filing.created event's `data`. Task 7 fills it from EDGAR.
SAMPLE_FILING = {
    "ticker": "AAPL",
    "company": "Apple Inc.",
    "cik": 320193,
    "form": "10-K",
    "filing_date": "2025-10-31",
    "accession_number": "0000320193-25-000079",
    "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
}


async def send(event_type: EventType) -> None:
    settings = get_settings()
    if settings.n8n_webhook_url is None or settings.webhook_signing_secret is None:
        sys.exit("Set N8N_WEBHOOK_URL and WEBHOOK_SIGNING_SECRET in .env first")

    data = SAMPLE_FILING if event_type == "filing.created" else {}
    event = WebhookEvent(type=event_type, data=data)
    async with WebhookDispatcher(
        settings.n8n_webhook_url, settings.webhook_signing_secret.get_secret_value()
    ) as dispatcher:
        try:
            await dispatcher.send(event)
        except WebhookDeliveryError as err:
            sys.exit(f"Not delivered: {err}")
    print(f"Delivered {event.type} {event.id}")


def main() -> None:
    event_type = sys.argv[1] if len(sys.argv) > 1 else "filing.created"
    if event_type not in get_args(EventType):
        sys.exit(f"Unknown event type {event_type!r}; one of {get_args(EventType)}")
    asyncio.run(send(event_type))  # type: ignore[arg-type]  # checked against EventType above


if __name__ == "__main__":
    main()
