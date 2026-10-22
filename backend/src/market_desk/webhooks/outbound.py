"""Outbound webhooks: sign an event and POST it, retrying on failure (ADR-0005)."""

import asyncio
import logging
import types
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx2
from standardwebhooks import Webhook
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from market_desk.webhooks.events import WebhookEvent

logger = logging.getLogger(__name__)


MAX_ATTEMPTS = 3


class WebhookDeliveryError(Exception):
    """The event couldn't be delivered: retries ran out, or the receiver refused it (4xx)."""


class WebhookEndpointGoneError(WebhookDeliveryError):
    """410 Gone: the receiver says this URL is closed for good. Stop sending to it."""


class WebhookRateLimitError(WebhookDeliveryError):
    """429"""

    def __init__(self, message: str, retry_after: float | None) -> None:
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)


class WebhookServerError(WebhookDeliveryError):
    """5xx"""


class WebhookConnectionError(WebhookDeliveryError):
    """connection issues, timeouts, etc."""


class WebhookDispatcher:
    """Sends signed events to one URL. Use as `async with WebhookDispatcher(...) as dispatcher:`."""

    def __init__(
        self,
        url: str,
        secret: str,
        *,
        timeout: float = 10.0,
        transport: httpx2.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._url = url  # the receiver's full URL, used as given
        self._secret = Webhook(secret)
        self.client = httpx2.AsyncClient(timeout=timeout, transport=transport)
        self._sleep = sleep

    async def __aenter__(self) -> "WebhookDispatcher":
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

    async def send(self, event: WebhookEvent) -> None:
        """POST the event, signed. Returns on a 2xx; raises WebhookDeliveryError otherwise.

        Retries 5xx, 429 and network errors with the same webhook-id; each attempt gets a fresh
        timestamp and signature (a retry is a new delivery, and an old timestamp would expire).
        """
        body = event.model_dump_json()  # serialized once: the exact string signed AND sent
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_should_retry),
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=_wait,
            sleep=self._sleep,
            reraise=True,
            before_sleep=_log_retry,
        ):
            with attempt:
                timestamp = datetime.now(UTC)  # aware UTC: sign() would mislabel a naive time
                headers = {
                    "webhook-id": event.id,
                    "webhook-timestamp": str(int(timestamp.timestamp())),
                    "webhook-signature": self._secret.sign(
                        msg_id=event.id, timestamp=timestamp, data=body
                    ),
                    "Content-Type": "application/json",
                }
                try:
                    response = await self.client.post(self._url, content=body, headers=headers)
                except httpx2.TransportError as err:  # timeouts, DNS, connection refused...
                    raise WebhookConnectionError(f"POST {self._url}: no response") from err
                self._raise_for_error(response)
                return  # inside `with attempt`: a success ends the retry loop
        raise AssertionError("unreachable")  # mypy: reraise=True never reaches here

    @staticmethod
    def _raise_for_error(response: httpx2.Response) -> None:
        """Only a 2xx is a delivery (Standard Webhooks); anything else raises."""
        if response.is_success:
            return

        status_code = response.status_code
        if status_code == 410:
            raise WebhookEndpointGoneError(f"{response.url} is gone (410): stop sending to it")

        if status_code == 429:
            raise WebhookRateLimitError(
                f"{response.url} is rate limiting (429)",
                retry_after=_parse_retry_after(response.headers.get("retry-after")),
            )

        if response.is_server_error:
            raise WebhookServerError(f"{response.url} failed ({status_code})")

        # Other 4xx, and 3xx too: the spec says don't follow redirects, fix the URL instead
        raise WebhookDeliveryError(
            f"{response.url} refused the event ({status_code}): {response.text[:200]}"
        )


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


_backoff = wait_exponential_jitter(multiplier=0.5, max=8)


def _wait(retry_state: RetryCallState) -> float:
    """How long to wait: Webhook Retry-After if it gave one, else exponential backoff."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, WebhookRateLimitError) and exc.retry_after is not None:
        return exc.retry_after
    return _backoff(retry_state)


def _should_retry(exc: BaseException) -> bool:
    return isinstance(exc, (WebhookRateLimitError, WebhookServerError, WebhookConnectionError))


def _log_retry(retry_state: RetryCallState) -> None:
    """One WARNING per retry: which attempt failed, why, and how long until the next one."""
    logger.warning(
        "Webhook request failed (%s); attempt %d, retrying in %.1fs",
        retry_state.outcome.exception() if retry_state.outcome else None,
        retry_state.attempt_number,
        # %.1f can't format None; next_action is always set in before_sleep, but don't bet the log
        retry_state.next_action.sleep if retry_state.next_action else 0.0,
    )
