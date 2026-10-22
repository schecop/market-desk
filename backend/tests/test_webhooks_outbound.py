"""Outbound webhooks: events are signed, delivered, and retried only when it makes sense."""

import base64
import json

import httpx2
import pytest
from standardwebhooks import Webhook

from market_desk.webhooks.events import WebhookEvent
from market_desk.webhooks.outbound import (
    WebhookDeliveryError,
    WebhookDispatcher,
    WebhookEndpointGoneError,
)

SECRET = "whsec_" + base64.b64encode(bytes(range(32))).decode()
URL = "https://n8n.example.test/webhook/market-desk"


def scripted_receiver(
    responses: list[httpx2.Response], seen: list[httpx2.Request]
) -> httpx2.MockTransport:
    """A fake receiver: records each delivery and answers with the next scripted response."""
    remaining = iter(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return next(remaining)

    return httpx2.MockTransport(handler)


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_dispatcher(transport: httpx2.MockTransport) -> WebhookDispatcher:
    return WebhookDispatcher(URL, SECRET, transport=transport, sleep=FakeSleep())


def ping() -> WebhookEvent:
    return WebhookEvent(type="test.ping", data={"hello": "world"})


# --- delivered ---


@pytest.mark.anyio
async def test_event_is_posted_as_json_to_the_url() -> None:
    seen: list[httpx2.Request] = []
    event = ping()

    async with make_dispatcher(scripted_receiver([httpx2.Response(204)], seen)) as dispatcher:
        await dispatcher.send(event)

    assert [(r.method, str(r.url)) for r in seen] == [("POST", URL)]
    sent = json.loads(seen[0].content)
    assert (sent["id"], sent["type"]) == (event.id, "test.ping")
    assert seen[0].headers["Content-Type"] == "application/json"


@pytest.mark.anyio
async def test_receiver_can_verify_the_signature() -> None:
    # The real check: a receiver with the same secret accepts what we sent
    seen: list[httpx2.Request] = []

    async with make_dispatcher(scripted_receiver([httpx2.Response(200)], seen)) as dispatcher:
        await dispatcher.send(ping())

    # What a receiver does: raises WebhookVerificationError if anything doesn't match
    verified = Webhook(SECRET).verify(seen[0].content, dict(seen[0].headers))
    assert verified["type"] == "test.ping"


# --- retried ---


@pytest.mark.anyio
async def test_server_error_is_retried_with_the_same_id() -> None:
    seen: list[httpx2.Request] = []
    event = ping()
    receiver = scripted_receiver([httpx2.Response(503), httpx2.Response(200)], seen)

    async with make_dispatcher(receiver) as dispatcher:
        await dispatcher.send(event)

    # The same id on every attempt: the receiver dedupes on it
    assert [r.headers["webhook-id"] for r in seen] == [event.id, event.id]


@pytest.mark.anyio
async def test_retries_exhausted_raise_delivery_error() -> None:
    seen: list[httpx2.Request] = []
    receiver = scripted_receiver([httpx2.Response(500)] * 3, seen)

    async with make_dispatcher(receiver) as dispatcher:
        with pytest.raises(WebhookDeliveryError):
            await dispatcher.send(ping())

    assert len(seen) == 3


@pytest.mark.anyio
async def test_network_error_is_retried() -> None:
    seen: list[httpx2.Request] = []
    attempts = iter(["timeout", "ok"])

    def flaky(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if next(attempts) == "timeout":
            raise httpx2.ConnectTimeout("receiver unreachable", request=request)
        return httpx2.Response(200)

    async with make_dispatcher(httpx2.MockTransport(flaky)) as dispatcher:
        await dispatcher.send(ping())

    # Reaching this line means send() returned normally after the retry
    assert len(seen) == 2


# --- not retried ---


@pytest.mark.anyio
async def test_client_error_is_not_retried() -> None:
    seen: list[httpx2.Request] = []
    receiver = scripted_receiver([httpx2.Response(400, text="bad payload")], seen)

    async with make_dispatcher(receiver) as dispatcher:
        with pytest.raises(WebhookDeliveryError):
            await dispatcher.send(ping())

    # A 400 won't change on retry
    assert len(seen) == 1


@pytest.mark.anyio
async def test_gone_raises_endpoint_gone() -> None:
    seen: list[httpx2.Request] = []
    receiver = scripted_receiver([httpx2.Response(410)], seen)

    async with make_dispatcher(receiver) as dispatcher:
        with pytest.raises(WebhookEndpointGoneError) as exc_info:
            await dispatcher.send(ping())

    assert len(seen) == 1
    # A subclass: callers that only catch WebhookDeliveryError still handle it
    assert isinstance(exc_info.value, WebhookDeliveryError)
