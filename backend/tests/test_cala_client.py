"""Cala client tests: every request goes through an injected MockTransport, never the real API."""

from uuid import UUID

import httpx2
import pytest
from pydantic import SecretStr

from market_desk.clients.cala import CalaClient, CalaConfigError, Entity
from market_desk.config import Settings

API_KEY = "test-key"
APPLE = {
    "id": "e5bb591a-d308-4aa5-9672-96046d366cde",
    "name": "Apple Inc.",
    "entity_type": "Company",
    "description": "Consumer electronics company.",
}


def make_transport(response: httpx2.Response, seen: list[httpx2.Request]) -> httpx2.MockTransport:
    """A fake Cala: records every request it receives and answers with `response`."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return response

    return httpx2.MockTransport(handler)


@pytest.mark.anyio
async def test_search_entities_sends_the_right_request() -> None:
    seen: list[httpx2.Request] = []
    transport = make_transport(httpx2.Response(200, json={"entities": [APPLE]}), seen)

    async with CalaClient(api_key=API_KEY, timeout=5, transport=transport) as client:
        await client.search_entities("Apple", limit=5)

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert request.url.host == "api.cala.ai"
    assert request.url.path == "/v1/entities"
    assert request.url.params["name"] == "Apple"
    assert request.url.params["limit"] == "5"
    assert request.headers["X-API-KEY"] == API_KEY


@pytest.mark.anyio
async def test_search_entities_returns_typed_entities() -> None:
    no_description = {k: v for k, v in APPLE.items() if k != "description"}
    body = {"entities": [APPLE, no_description]}
    transport = make_transport(httpx2.Response(200, json=body), [])

    async with CalaClient(api_key=API_KEY, timeout=5, transport=transport) as client:
        entities = await client.search_entities("Apple")

    assert entities[0] == Entity(
        id=UUID(APPLE["id"]),
        name="Apple Inc.",
        entity_type="Company",
        description="Consumer electronics company.",
    )
    # "description" is optional in Cala's spec: a missing key becomes None
    assert entities[1].description is None


@pytest.mark.anyio
async def test_client_is_closed_after_async_with() -> None:
    transport = make_transport(httpx2.Response(200, json={"entities": []}), [])

    async with CalaClient(api_key=API_KEY, timeout=5, transport=transport) as client:
        assert not client.client.is_closed

    assert client.client.is_closed


def test_from_settings_without_key_raises() -> None:
    # Explicit argument beats .env, so the real key never leaks into the test
    settings = Settings(cala_api_key=None)

    with pytest.raises(CalaConfigError):
        CalaClient.from_settings(settings, timeout=5)


@pytest.mark.anyio
async def test_from_settings_uses_the_key() -> None:
    settings = Settings(cala_api_key=SecretStr(API_KEY))

    async with CalaClient.from_settings(settings, timeout=5) as client:
        assert client.client.headers["X-API-KEY"] == API_KEY
