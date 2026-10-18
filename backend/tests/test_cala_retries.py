"""Cala client retries (tenacity): what is retried, how long it waits, when it gives up.

Assumed client API (step 3 adds it): CalaClient(..., transport=..., sleep=...), where `sleep`
defaults to asyncio.sleep and tests pass a FakeSleep, so nothing really waits.
Build the client with: CalaClient(api_key="test-key", timeout=5, transport=..., sleep=fake_sleep)
"""

import logging
from typing import Literal

import httpx2
import pytest

from market_desk.clients.cala import (
    CalaClient,
    CalaConnectionError,
    CalaRateLimitError,
    CalaServerError,
    CalaValidationError,
)

ENTITIES_BODY = {
    "entities": [
        {
            "id": "e5bb591a-d308-4aa5-9672-96046d366cde",
            "name": "Apple Inc.",
            "entity_type": "Company",
        }
    ]
}
RATE_LIMIT_BODY = {"error": "rate_limit_exceeded", "message": "Rate limit exceeded."}

# One step of a scripted conversation with the fake Cala: a response, or a network timeout
Step = httpx2.Response | Literal["timeout"]


def scripted_transport(steps: list[Step], seen: list[httpx2.Request]) -> httpx2.MockTransport:
    """A fake Cala that answers each request with the next step, in order.

    Records every request in `seen`, so a test can count attempts. Raises StopIteration
    if the client sends more requests than there are steps (a test bug, or too many retries).
    """
    remaining = iter(steps)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        step = next(remaining)
        if step == "timeout":
            raise httpx2.ReadTimeout("timed out", request=request)
        return step

    return httpx2.MockTransport(handler)


class FakeSleep:
    """Stands in for asyncio.sleep: records each wait and returns at once."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


# --- retried, then recovers ---


@pytest.mark.anyio
async def test_429_then_200_retries_and_honours_retry_after() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # 429 with Retry-After + 200
    transport = scripted_transport(
        [
            httpx2.Response(429, json=RATE_LIMIT_BODY, headers={"retry-after": "2"}),
            httpx2.Response(200, json=ENTITIES_BODY),
        ],
        seen,
    )

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        await client.search_entities("Apple")

    assert len(seen) == 2
    assert len(fake_sleep.calls) == 1
    assert fake_sleep.calls == [2.0]


@pytest.mark.anyio
async def test_timeout_then_200_recovers() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # timeout, then 200 OK
    transport = scripted_transport(["timeout", httpx2.Response(200, json=ENTITIES_BODY)], seen)

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        await client.search_entities("Apple")

    assert len(seen) == 2
    request = seen[1]
    assert request.url.params["name"] == "Apple"


@pytest.mark.anyio
async def test_429_without_retry_after_uses_backoff() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # 429 + 200
    transport = scripted_transport(
        [httpx2.Response(429, json={"error": {}}), httpx2.Response(200, json=ENTITIES_BODY)], seen
    )

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        await client.search_entities("Apple")

    assert len(seen) == 2
    assert len(fake_sleep.calls) == 1
    assert fake_sleep.calls[0] > 0


# --- retried until it gives up ---


@pytest.mark.anyio
async def test_500_three_times_raises_server_error() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # 3 server errors are retried
    transport = scripted_transport(
        [
            httpx2.Response(500, json={"error": {}}),
            httpx2.Response(500, json={"error": {}}),
            httpx2.Response(500, json={"error": {}}),
        ],
        seen,
    )

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        with pytest.raises(CalaServerError):
            await client.search_entities("Apple")

    assert len(seen) == 3


@pytest.mark.anyio
async def test_timeouts_exhausted_raise_a_cala_error() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # 3 timeouts
    transport = scripted_transport(["timeout", "timeout", "timeout"], seen)

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        with pytest.raises(CalaConnectionError):
            await client.search_entities("Apple")

    assert len(seen) == 3


# --- never retried ---


@pytest.mark.anyio
async def test_422_is_not_retried() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # Only one step: if the client retried, the second request would hit StopIteration
    transport = scripted_transport([httpx2.Response(422, json={"error": {}})], seen)

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        with pytest.raises(CalaValidationError):
            await client.search_entities("Apple")

    assert len(seen) == 1
    assert fake_sleep.calls == []


# --- limits and logging ---


@pytest.mark.anyio
async def test_huge_retry_after_does_not_block() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # 429 with HUGE Retry-After + 200
    transport = scripted_transport(
        [
            httpx2.Response(429, json=RATE_LIMIT_BODY, headers={"retry-after": "3600"}),
            httpx2.Response(200, json=ENTITIES_BODY),
        ],
        seen,
    )

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        with pytest.raises(CalaRateLimitError):
            await client.search_entities("Apple")

    assert len(seen) == 1
    assert fake_sleep.calls == []


@pytest.mark.anyio
async def test_each_retry_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    seen: list[httpx2.Request] = []
    transport = scripted_transport(
        [
            httpx2.Response(429, json=RATE_LIMIT_BODY, headers={"Retry-After": "2"}),
            httpx2.Response(200, json=ENTITIES_BODY),
        ],
        seen,
    )

    # at_level is a context manager: it captures WARNING and above only inside the block
    with caplog.at_level(logging.WARNING, logger="market_desk.clients.cala"):
        async with CalaClient(
            api_key="test-key", timeout=5, transport=transport, sleep=FakeSleep()
        ) as client:
            await client.search_entities("Apple")

    # One retry → exactly one log line, from our logger, at WARNING
    assert len(seen) == 2
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.name == "market_desk.clients.cala"
    assert record.levelno == logging.WARNING
    # The message says which attempt failed and how long it will wait
    assert "attempt 1" in record.getMessage()
    assert "2.0s" in record.getMessage()
