"""EDGAR dev cache (hishel, ADR-0004): repeat requests stay off the network; errors aren't kept."""

from pathlib import Path

import httpx2
import pytest
from aiolimiter import AsyncLimiter

from market_desk.clients.edgar import EdgarClient, EdgarServerError, dev_cache_transport
from market_desk.config import Settings

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
TICKERS_BODY = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


class FakeSleep:
    async def __call__(self, seconds: float) -> None:
        return None


def counting_network(
    responses: list[httpx2.Response], seen: list[httpx2.Request]
) -> httpx2.MockTransport:
    """Stands in for the real network behind the cache: counts what actually gets through."""
    remaining = iter(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return next(remaining)

    return httpx2.MockTransport(handler)


def cached_client(cache_dir: Path, network: httpx2.MockTransport) -> EdgarClient:
    return EdgarClient(
        user_agent="Market Desk tests@example.com",
        timeout=5,
        transport=dev_cache_transport(cache_dir, next_transport=network),
        limiter=AsyncLimiter(10_000, 1),
        sleep=FakeSleep(),
    )


@pytest.mark.anyio
async def test_repeat_request_is_served_from_the_cache(tmp_path: Path) -> None:
    seen: list[httpx2.Request] = []
    network = counting_network([httpx2.Response(200, json=TICKERS_BODY)], seen)

    async with cached_client(tmp_path, network) as client:
        first = await client.client.get(TICKERS_URL)
        second = await client.client.get(TICKERS_URL)

    assert len(seen) == 1  # only the first request reached the network
    assert second.json() == first.json()
    assert second.extensions.get("hishel_from_cache") is True


@pytest.mark.anyio
async def test_cache_survives_a_new_client(tmp_path: Path) -> None:
    # It lives on disk (SQLite), so a second run of the app (a new client) starts warm
    seen: list[httpx2.Request] = []

    async with cached_client(
        tmp_path, counting_network([httpx2.Response(200, json=TICKERS_BODY)], seen)
    ) as client:
        assert await client.get_cik("AAPL") == 320193

    async with cached_client(tmp_path, counting_network([], seen)) as client:
        assert await client.get_cik("AAPL") == 320193  # an empty network: it must come from disk

    assert len(seen) == 1
    assert (tmp_path / "edgar.sqlite").exists()


@pytest.mark.anyio
async def test_errors_are_not_cached(tmp_path: Path) -> None:
    # Without the 200-only filter, one SEC hiccup would be replayed until the cache is deleted
    seen: list[httpx2.Request] = []
    network = counting_network(
        [httpx2.Response(500, text="down")] * 3 + [httpx2.Response(200, json=TICKERS_BODY)], seen
    )

    async with cached_client(tmp_path, network) as client:
        with pytest.raises(EdgarServerError):
            await client.get_cik("AAPL")  # 3 attempts, all 500
        assert await client.get_cik("AAPL") == 320193  # the 500s weren't kept

    assert len(seen) == 4


@pytest.mark.anyio
async def test_from_settings_with_cache_dir_creates_it(tmp_path: Path) -> None:
    # Only builds the client (no request is sent), so the real network is never touched
    cache_dir = tmp_path / "edgar-cache"
    settings = Settings(
        edgar_user_agent="Market Desk tests@example.com", edgar_cache_dir=str(cache_dir)
    )

    async with EdgarClient.from_settings(settings, timeout=5):
        assert cache_dir.is_dir()
