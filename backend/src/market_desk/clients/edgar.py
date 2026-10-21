"""Typed async client for SEC EDGAR: ticker → CIK, filings, documents (ADR-0003, ADR-0004)."""

import asyncio
import logging
import types
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path
from typing import Any

import hishel
import httpx2
from aiolimiter import AsyncLimiter
from hishel.httpx2 import AsyncCacheTransport
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from market_desk.config import Settings

logger = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"  # CIK padded to 10 digits
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

# Retry policy (ADR-0003). EDGAR has no quota, but every retry still counts towards 10 req/s.
MAX_ATTEMPTS = 3
MAX_RETRY_AFTER = 30.0  # seconds; a longer Retry-After fails fast instead of blocking the agent


class Filing(BaseModel):
    accession_number: str
    form: str
    filing_date: date
    report_date: date | None
    primary_document: str


class EdgarError(Exception):
    """Base class: anything that goes wrong talking to EDGAR. Other 4xx raise it directly."""


class EdgarConfigError(EdgarError):
    """The client can't be built (no User-Agent). Not retried."""


class EdgarNotFoundError(EdgarError):
    """404, or a ticker that isn't in the SEC's list. Not retried."""


class EdgarForbiddenError(EdgarError):
    """403: the SEC blocks a missing User-Agent or too many requests. Not retried."""


class EdgarRateLimitError(EdgarError):
    """429: too many requests. retry_after is seconds to wait, or None if EDGAR didn't say."""

    def __init__(self, message: str, retry_after: float | None) -> None:
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)


class EdgarServerError(EdgarError):
    """5xx: a failure on EDGAR's side, usually temporary. Retried."""


class EdgarResponseError(EdgarError):
    """A success whose body doesn't have the expected shape: EDGAR changed it. Not retried."""


class EdgarConnectionError(EdgarError):
    """Timeout or network failure: no response at all. Retried."""


class EdgarClient:
    """Async client for EDGAR. Use as `async with EdgarClient.from_settings(...) as client:`.

    Stays under the SEC's 10 requests/second with a shared limiter. Every method returns
    models or plain values, or raises an EdgarError subclass, never an httpx2 error.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        timeout: float,
        transport: httpx2.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        limiter: AsyncLimiter | None = None,
    ) -> None:
        # ticker → CIK, filled by the first get_cik() call. None means "not downloaded yet".
        # Created here, per instance, so two clients never share it.
        self._ciks: dict[str, int] | None = None

        headers = {"User-Agent": user_agent}
        self.client = httpx2.AsyncClient(headers=headers, timeout=timeout, transport=transport)
        self._sleep = sleep
        self._limiter = AsyncLimiter(10, 1) if limiter is None else limiter

    @classmethod
    def from_settings(cls, settings: Settings, timeout: float) -> "EdgarClient":
        """Build from app settings. With EDGAR_CACHE_DIR set (development), responses are cached."""
        if settings.edgar_user_agent is None:
            raise EdgarConfigError("No EDGAR User-Agent: set EDGAR_USER_AGENT in .env")

        cache_dir = settings.edgar_cache_dir
        transport = dev_cache_transport(cache_dir) if cache_dir else None  # None: real network
        return cls(settings.edgar_user_agent, timeout=timeout, transport=transport)

    async def __aenter__(self) -> "EdgarClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self.client.aclose()

    async def get_cik(self, ticker: str) -> int:
        """The company's CIK for a ticker, case-insensitive. Downloads the SEC's list once."""
        if self._ciks is None:
            response = await self._request("GET", TICKERS_URL)
            # The file is keyed by position ("0", "1"...): re-key it by ticker, once
            try:
                companies = _json(response).values()
                self._ciks = {c["ticker"].upper(): int(c["cik_str"]) for c in companies}
            except (AttributeError, KeyError, TypeError, ValueError) as err:
                raise EdgarResponseError(f"Unexpected tickers file: {_snippet(response)}") from err

        try:
            return self._ciks[ticker.upper()]
        except KeyError:
            raise EdgarNotFoundError(f"Ticker {ticker!r} is not in the SEC's list") from None

    async def list_filings(self, cik: int, form: str = "10-K", limit: int = 10) -> list[Filing]:
        """The company's most recent filings of one form, newest first (at most `limit`)."""
        response = await self._request("GET", SUBMISSIONS_URL.format(cik=cik))

        try:
            # Columns, not rows: parallel lists, one per field
            recent = _json(response)["filings"]["recent"]
            rows = zip(
                recent["accessionNumber"],
                recent["form"],
                recent["filingDate"],
                recent["reportDate"],
                recent["primaryDocument"],
                strict=True,  # columns of different lengths are a broken response, not a guess
            )
            filings = [
                Filing(
                    accession_number=accession,
                    form=row_form,
                    filing_date=filed,
                    report_date=reported or None,  # "" in some forms (e.g. 144): not a date
                    primary_document=document,
                )
                for accession, row_form, filed, reported, document in rows
                if row_form == form
            ]
        except (KeyError, TypeError, ValueError, ValidationError) as err:
            raise EdgarResponseError(
                f"Unexpected submissions for CIK {cik}: {_snippet(response)}"
            ) from err

        return filings[:limit]

    async def fetch_document(self, cik: int, filing: Filing) -> str:
        """A filing's primary document (HTML; inline XBRL for 10-K and 10-Q)."""
        url = ARCHIVES_URL.format(
            cik=cik,
            accession=filing.accession_number.replace("-", ""),
            document=filing.primary_document,
        )
        response = await self._request("GET", url)
        return response.text

    async def _request(self, method: str, url: str) -> httpx2.Response:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_should_retry),
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=_wait,
            sleep=self._sleep,
            reraise=True,
            before_sleep=_log_retry,
        ):
            # Inside the loop: every attempt, retries included, counts towards 10 req/s
            async with self._limiter:
                with attempt:
                    try:
                        response = await self.client.request(method, url)
                    except httpx2.TransportError as err:  # timeouts, DNS, connection refused...
                        raise EdgarConnectionError(f"{method} {url}: no response") from err
                    self._raise_for_error(response)
                    return response  # inside `with attempt`: a success ends the retry loop
        raise AssertionError("unreachable")  # mypy: reraise=True never reaches here

    @staticmethod
    def _raise_for_error(response: httpx2.Response) -> None:
        """Map an error status to an EdgarError subclass. The status decides the type."""
        status_code = response.status_code

        if status_code == 403:
            raise EdgarForbiddenError(f"EDGAR forbidden (403): {_snippet(response)}")

        if status_code == 404:
            raise EdgarNotFoundError(f"EDGAR not found (404): {response.request.url}")

        if status_code == 429:
            raise EdgarRateLimitError(
                "Rate limit exceeded", _parse_retry_after(response.headers.get("retry-after"))
            )

        if response.is_server_error:
            raise EdgarServerError(f"EDGAR server error {status_code}: {_snippet(response)}")

        if response.is_client_error:
            raise EdgarError(f"EDGAR client error {status_code}: {_snippet(response)}")


class _OnlySuccess(hishel.BaseFilter[hishel.Response]):
    """Store only 200s: a cached 500 or 403 would be served back until the cache is deleted."""

    def needs_body(self) -> bool:
        return False

    def apply(self, item: hishel.Response, body: bytes | None) -> bool:
        return item.status_code == 200


def dev_cache_transport(
    cache_dir: str | Path, next_transport: httpx2.AsyncBaseTransport | None = None
) -> AsyncCacheTransport:
    """A transport that caches successful EDGAR responses on disk, for development (ADR-0004).

    FilterPolicy instead of the HTTP caching rules (RFC 9111): the SEC sends `max-age=6` or no
    Cache-Control at all, so standard rules would cache almost nothing. Filings never change;
    a cached submissions list can go stale (delete the cache dir to refresh).
    `next_transport` is the real network by default; tests pass a MockTransport.
    """
    path = Path(cache_dir)
    path.mkdir(parents=True, exist_ok=True)
    return AsyncCacheTransport(
        next_transport=next_transport or httpx2.AsyncHTTPTransport(),
        storage=hishel.AsyncSqliteStorage(database_path=path / "edgar.sqlite"),
        policy=hishel.FilterPolicy(response_filters=[_OnlySuccess()]),
    )


def _json(response: httpx2.Response) -> Any:
    """The parsed body. Raises ValueError if it isn't JSON: callers map it to EdgarResponseError."""
    return response.json()


def _parse_retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header; None if missing or not a non-negative number.

    The header may also be an HTTP date; the SEC doesn't document it, so that counts as unknown.
    """
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _snippet(response: httpx2.Response, limit: int = 200) -> str:
    """The start of the body, for error messages: enough to debug, not a whole HTML page."""
    return response.text[:limit]


_backoff = wait_exponential_jitter(multiplier=0.5, max=8)


def _wait(retry_state: RetryCallState) -> float:
    """How long to wait: EDGAR's Retry-After if it gave one, else exponential backoff."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, EdgarRateLimitError) and exc.retry_after is not None:
        return exc.retry_after
    return _backoff(retry_state)


def _should_retry(exc: BaseException) -> bool:
    """Retry rate limits (unless EDGAR asks for too long a wait), 5xx and network failures."""
    if isinstance(exc, EdgarRateLimitError) and exc.retry_after is not None:
        return exc.retry_after <= MAX_RETRY_AFTER
    return isinstance(exc, (EdgarRateLimitError, EdgarServerError, EdgarConnectionError))


def _log_retry(retry_state: RetryCallState) -> None:
    """One WARNING per retry: which attempt failed, why, and how long until the next one."""
    logger.warning(
        "EDGAR request failed (%s); attempt %d, retrying in %.1fs",
        retry_state.outcome.exception() if retry_state.outcome else None,
        retry_state.attempt_number,
        # %.1f can't format None; next_action is always set in before_sleep, but don't bet the log
        retry_state.next_action.sleep if retry_state.next_action else 0.0,
    )
