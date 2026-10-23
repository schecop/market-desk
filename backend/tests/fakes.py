"""Fakes shared by the watchlist and filing-check tests: a fake SEC and a fake n8n.

Apple's submissions fixture has three 10-Ks: NEWEST and the two OLDER ones.
"""

import base64
import json
from pathlib import Path
from typing import Any

import httpx2
from aiolimiter import AsyncLimiter

from market_desk.clients.edgar import EdgarClient
from market_desk.webhooks.outbound import WebhookDispatcher

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"
SEC_ROUTES = {
    "https://www.sec.gov/files/company_tickers.json": "company_tickers.json",
    "https://data.sec.gov/submissions/CIK0000320193.json": "submissions_CIK0000320193.json",
}
SECRET = "whsec_" + base64.b64encode(b"0" * 32).decode()
N8N_URL = "https://n8n.test/webhook/market-desk"

APPLE_CIK = 320193
NEWEST = "0000320193-25-000079"  # filed 2025-10-31
OLDER = ["0000320193-24-000123", "0000320193-23-000106"]


async def no_sleep(seconds: float) -> None:
    pass


def fake_sec(request: httpx2.Request) -> httpx2.Response:
    """Known URLs answer with their fixture; anything else is a 404, like the SEC."""
    name = SEC_ROUTES.get(str(request.url))
    if name is None:
        return httpx2.Response(404)
    return httpx2.Response(200, content=(FIXTURES / name).read_bytes())


def make_edgar() -> EdgarClient:
    """An EDGAR client on the fake SEC: no network, no waiting, no rate limit."""
    return EdgarClient(
        "Market Desk tests@example.com",
        timeout=5,
        transport=httpx2.MockTransport(fake_sec),
        sleep=no_sleep,
        limiter=AsyncLimiter(10_000, 1),
    )


class FakeN8n:
    """Records every event it receives and answers with `status` (202 unless a test changes it)."""

    def __init__(self) -> None:
        self.status = 202
        self.events: list[dict[str, Any]] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.events.append(json.loads(request.content))
        return httpx2.Response(self.status)

    def dispatcher(self) -> WebhookDispatcher:
        return WebhookDispatcher(
            N8N_URL, SECRET, transport=httpx2.MockTransport(self.handler), sleep=no_sleep
        )
