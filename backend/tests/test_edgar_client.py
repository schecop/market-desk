"""EDGAR client: ticker → CIK, filings list, documents, errors. Fixtures are trimmed real responses.

make_client(...) builds a client with no network, no real waiting and an unlimited limiter;
fixture_transport routes each known URL to its fixture and answers 404 for anything else.
"""

from datetime import date
from pathlib import Path

import httpx2
import pytest
from aiolimiter import AsyncLimiter

from market_desk.clients.edgar import (
    EdgarClient,
    EdgarConfigError,
    EdgarForbiddenError,
    EdgarNotFoundError,
    EdgarResponseError,
    EdgarServerError,
)
from market_desk.config import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"
USER_AGENT = "Market Desk tests@example.com"
APPLE_CIK = 320193

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
APPLE_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0000320193.json"
# Apple's FY2025 10-K, as listed in the submissions fixture
APPLE_10K_URL = (
    "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"
)

ROUTES = {
    TICKERS_URL: ("company_tickers.json", "application/json"),
    APPLE_SUBMISSIONS_URL: ("submissions_CIK0000320193.json", "application/json"),
    APPLE_10K_URL: ("aapl_10k_head.htm", "text/html"),
}


def fixture_transport(seen: list[httpx2.Request]) -> httpx2.MockTransport:
    """A fake SEC: known URLs answer with their fixture; any other URL is a 404, like the SEC."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        route = ROUTES.get(str(request.url))
        if route is None:
            return httpx2.Response(404, text="<html>Not Found</html>")
        name, content_type = route
        return httpx2.Response(
            200, content=(FIXTURES / name).read_bytes(), headers={"Content-Type": content_type}
        )

    return httpx2.MockTransport(handler)


class FakeSleep:
    """Stands in for asyncio.sleep: records each wait and returns at once."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_client(
    transport: httpx2.MockTransport, limiter: AsyncLimiter | None = None
) -> EdgarClient:
    """A client with no network, no real waiting and, by default, a limiter that never blocks."""
    return EdgarClient(
        user_agent=USER_AGENT,
        timeout=5,
        transport=transport,
        limiter=limiter or AsyncLimiter(10_000, 1),
        sleep=FakeSleep(),
    )


# --- ticker → CIK ---


@pytest.mark.anyio
async def test_get_cik_for_known_ticker() -> None:
    seen: list[httpx2.Request] = []

    async with make_client(fixture_transport(seen)) as client:
        cik = await client.get_cik("AAPL")

    assert cik == APPLE_CIK
    # The tickers file stores it as an int ("cik_str" despite the name): keep it that way
    assert isinstance(cik, int)
    assert [str(r.url) for r in seen] == [TICKERS_URL]


@pytest.mark.anyio
async def test_get_cik_is_case_insensitive() -> None:
    async with make_client(fixture_transport([])) as client:
        assert await client.get_cik("aapl") == APPLE_CIK
        assert await client.get_cik("Msft") == 789019


@pytest.mark.anyio
async def test_get_cik_downloads_tickers_once() -> None:
    seen: list[httpx2.Request] = []

    async with make_client(fixture_transport(seen)) as client:
        await client.get_cik("AAPL")
        await client.get_cik("MSFT")

    assert len(seen) == 1


@pytest.mark.anyio
async def test_get_cik_unknown_ticker_raises_not_found() -> None:
    async with make_client(fixture_transport([])) as client:
        with pytest.raises(EdgarNotFoundError) as exc_info:
            await client.get_cik("NOPE")

    # The message says *which* lookup failed, so a log line is useful on its own
    assert "NOPE" in str(exc_info.value)


@pytest.mark.anyio
async def test_two_clients_do_not_share_tickers() -> None:
    seen: list[httpx2.Request] = []

    async with make_client(fixture_transport(seen)) as client_a:
        await client_a.get_cik("AAPL")

    async with make_client(fixture_transport(seen)) as client_b:
        await client_b.get_cik("AAPL")

    assert len(seen) == 2


# --- filings list ---


@pytest.mark.anyio
async def test_list_filings_requests_zero_padded_cik() -> None:
    seen: list[httpx2.Request] = []

    async with make_client(fixture_transport(seen)) as client:
        await client.list_filings(APPLE_CIK)

    assert [str(r.url) for r in seen] == [APPLE_SUBMISSIONS_URL]


@pytest.mark.anyio
async def test_list_filings_returns_only_the_requested_form() -> None:
    # The fixture has 3 10-Ks and 4 10-Qs among 17 rows
    async with make_client(fixture_transport([])) as client:
        filings = await client.list_filings(APPLE_CIK, form="10-K")

    assert len(filings) == 3
    assert [filing.form for filing in filings] == ["10-K", "10-K", "10-K"]


@pytest.mark.anyio
async def test_list_filings_newest_first_and_limited() -> None:
    async with make_client(fixture_transport([])) as client:
        filings = await client.list_filings(APPLE_CIK, form="10-K", limit=2)

    assert len(filings) == 2
    assert filings[0].filing_date == date(2025, 10, 31)
    assert filings[0].accession_number == "0000320193-25-000079"
    assert filings[0].primary_document == "aapl-20250927.htm"


@pytest.mark.anyio
async def test_list_filings_parses_dates() -> None:
    async with make_client(fixture_transport([])) as client:
        filing = (await client.list_filings(APPLE_CIK, form="10-K", limit=1))[0]

    # Apple's FY2025 10-K: filed 2025-10-31 for the fiscal year ending 2025-09-27
    assert filing.filing_date == date(2025, 10, 31)
    assert filing.report_date == date(2025, 9, 27)


@pytest.mark.anyio
async def test_empty_report_date_becomes_none() -> None:
    # Form 144 rows in the fixture have reportDate "" (an empty string, not a date)
    async with make_client(fixture_transport([])) as client:
        filings = await client.list_filings(APPLE_CIK, form="144")

    assert len(filings) > 0
    assert all(filing.report_date is None for filing in filings)


# --- documents ---


@pytest.mark.anyio
async def test_fetch_document_builds_the_archives_url() -> None:
    seen: list[httpx2.Request] = []

    async with make_client(fixture_transport(seen)) as client:
        filing = (await client.list_filings(APPLE_CIK, form="10-K", limit=1))[0]
        text = await client.fetch_document(APPLE_CIK, filing)

    assert str(seen[-1].url) == APPLE_10K_URL
    assert text.startswith("<?xml")


# --- headers, errors, retries ---


@pytest.mark.anyio
async def test_every_request_sends_the_user_agent() -> None:
    seen: list[httpx2.Request] = []

    async with make_client(fixture_transport(seen)) as client:
        cik = await client.get_cik("AAPL")
        await client.list_filings(cik)

    assert len(seen) == 2
    assert [r.headers.get("User-Agent") for r in seen] == [USER_AGENT, USER_AGENT]


@pytest.mark.anyio
async def test_unknown_cik_raises_not_found() -> None:
    # The fake SEC answers 404 for any URL it doesn't know
    seen: list[httpx2.Request] = []

    async with make_client(fixture_transport(seen)) as client:
        with pytest.raises(EdgarNotFoundError):
            await client.list_filings(999999999)

    assert len(seen) == 1


@pytest.mark.anyio
async def test_server_errors_stop_after_three_attempts() -> None:
    seen: list[httpx2.Request] = []

    # A SEC that is down: every request gets a 500 (fixture_transport never returns one)
    def always_500(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500, text="<html>Internal Server Error</html>")

    async with make_client(httpx2.MockTransport(always_500)) as client:
        with pytest.raises(EdgarServerError):
            await client.get_cik("AAPL")

    # 3 attempts, then the error reaches the caller (not stop_never: retrying forever)
    assert len(seen) == 3
    assert all(str(r.url) == TICKERS_URL for r in seen)


@pytest.mark.anyio
async def test_403_raises_forbidden_and_is_not_retried() -> None:
    # The SEC answers 403 to a missing User-Agent or too many requests: retrying makes it worse
    seen: list[httpx2.Request] = []

    def always_403(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(403, text="<html>Request Rate Threshold Exceeded</html>")

    async with make_client(httpx2.MockTransport(always_403)) as client:
        with pytest.raises(EdgarForbiddenError):
            await client.get_cik("AAPL")

    assert len(seen) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        {"filings": {}},  # no "recent"
        {"filings": {"recent": {"form": ["10-K"]}}},  # columns missing
        {
            "filings": {
                "recent": {
                    **{k: [] for k in ("accessionNumber", "filingDate")},
                    "form": ["10-K"],
                    "reportDate": [],
                    "primaryDocument": [],
                }
            }
        },
    ],
    ids=["no-recent", "missing-columns", "uneven-columns"],
)
async def test_unexpected_submissions_shape_raises_response_error(body: object) -> None:
    def answer(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=body)

    async with make_client(httpx2.MockTransport(answer)) as client:
        with pytest.raises(EdgarResponseError):
            await client.list_filings(APPLE_CIK)


def test_from_settings_without_user_agent_raises() -> None:
    # Explicit argument beats .env, so your real User-Agent never leaks into the test
    settings = Settings(edgar_user_agent=None)

    with pytest.raises(EdgarConfigError):
        EdgarClient.from_settings(settings, 5)


# --- rate limiting (guided exercise) ---


class CountingLimiter(AsyncLimiter):
    """A real limiter (it still limits) that also counts how many times it was entered."""

    def __init__(self) -> None:
        super().__init__(10_000, 1)  # generous: the tests must never actually wait
        self.entered = 0

    async def __aenter__(self) -> None:
        self.entered += 1
        await super().__aenter__()


@pytest.mark.anyio
async def test_each_request_goes_through_the_limiter() -> None:
    limiter = CountingLimiter()

    async with make_client(fixture_transport([]), limiter=limiter) as client:
        await client.get_cik("AAPL")

    assert limiter.entered == 1


@pytest.mark.anyio
async def test_each_retry_goes_through_the_limiter() -> None:
    limiter = CountingLimiter()
    seen: list[httpx2.Request] = []

    def always_500(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(500, text="<html>Internal Server Error</html>")

    async with make_client(httpx2.MockTransport(always_500), limiter=limiter) as client:
        with pytest.raises(EdgarServerError):
            await client.get_cik("AAPL")

    assert len(seen) == 3
    assert limiter.entered == 3
