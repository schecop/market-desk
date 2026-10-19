"""Cala entity retrieval (POST /v1/entities/{entity_id}): request body, relationship paging."""

import json
from uuid import UUID

import httpx2
import pytest

from market_desk.clients.cala import CalaClient, EntityDetails

APPLE_ID = UUID("e5bb591a-d308-4aa5-9672-96046d366cde")

# Shaped like Cala's GetEntityResponse, with one page of outgoing relationships
ENTITY_WITH_RELATIONSHIPS = {
    "id": str(APPLE_ID),
    "name": "Apple Inc.",
    "entity_type": "Company",
    "description": "Consumer electronics company.",
    "properties": {"aliases": {"sources": [], "value": ["Apple", "AAPL"]}},
    "relationships": {
        "outgoing": {
            "IS_REGISTERED_IN": [
                {
                    "id": "37a1f0f5-f5ef-4b63-b3d8-14f5683e1e8a",
                    "name": "United States",
                    "entity_type": "Country",
                }
            ]
        },
        "incoming": {},
    },
}
# What Cala returns when no relationships were asked for
ENTITY_WITHOUT_RELATIONSHIPS = {
    "id": str(APPLE_ID),
    "name": "Apple Inc.",
    "entity_type": "Company",
    "properties": {},
    "relationships": {},
}


def recording_transport(
    response: httpx2.Response, seen: list[httpx2.Request]
) -> httpx2.MockTransport:
    """A fake Cala that records each request and always answers with `response`."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return response

    return httpx2.MockTransport(handler)


# --- the request ---


@pytest.mark.anyio
async def test_get_entity_without_relationship_sends_empty_body() -> None:
    seen: list[httpx2.Request] = []
    # 200 without rels
    transport = recording_transport(
        httpx2.Response(200, json=ENTITY_WITHOUT_RELATIONSHIPS),
        seen,
    )

    async with CalaClient(api_key="test-key", timeout=5, transport=transport) as client:
        await client.get_entity(APPLE_ID)

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert request.url.host == "api.cala.ai"
    assert request.url.path == f"/v1/entities/{APPLE_ID}"
    # No relationship asked for: send no query at all, so Cala returns its default properties
    assert json.loads(request.content) == {}


@pytest.mark.anyio
async def test_get_entity_with_relationship_sends_paging() -> None:
    seen: list[httpx2.Request] = []
    # 200 without rels
    transport = recording_transport(
        httpx2.Response(200, json=ENTITY_WITH_RELATIONSHIPS),
        seen,
    )

    async with CalaClient(api_key="test-key", timeout=5, transport=transport) as client:
        await client.get_entity(APPLE_ID, relationship="IS_REGISTERED_IN", limit=5, offset=10)

    assert len(seen) == 1
    request = seen[0]
    assert json.loads(request.content) == {
        "relationships": {"outgoing": {"IS_REGISTERED_IN": {"limit": 5, "offset": 10}}}
    }


@pytest.mark.anyio
async def test_any_relationship_type_is_sent() -> None:
    seen: list[httpx2.Request] = []
    # 200 without rels
    transport = recording_transport(
        httpx2.Response(200, json=ENTITY_WITH_RELATIONSHIPS),
        seen,
    )

    async with CalaClient(api_key="test-key", timeout=5, transport=transport) as client:
        await client.get_entity(APPLE_ID, relationship="HAS_SUBSIDIARY")

    assert len(seen) == 1
    request = seen[0]
    assert json.loads(request.content) == {
        "relationships": {"outgoing": {"HAS_SUBSIDIARY": {"limit": 10, "offset": 0}}}
    }


# --- the response ---


@pytest.mark.anyio
async def test_get_entity_parses_relationships() -> None:
    seen: list[httpx2.Request] = []
    # 200 without rels
    transport = recording_transport(
        httpx2.Response(200, json=ENTITY_WITH_RELATIONSHIPS),
        seen,
    )

    async with CalaClient(api_key="test-key", timeout=5, transport=transport) as client:
        response = await client.get_entity(APPLE_ID)

    assert isinstance(response, EntityDetails)
    assert response.properties["aliases"]
    assert response.relationships.outgoing["IS_REGISTERED_IN"][0]["name"] == "United States"


@pytest.mark.anyio
async def test_get_entity_with_empty_relationships() -> None:
    seen: list[httpx2.Request] = []
    # 200 without rels
    transport = recording_transport(
        httpx2.Response(200, json=ENTITY_WITHOUT_RELATIONSHIPS),
        seen,
    )

    async with CalaClient(api_key="test-key", timeout=5, transport=transport) as client:
        response = await client.get_entity(APPLE_ID)

    assert isinstance(response, EntityDetails)
    assert response.relationships.incoming == {}
    assert response.relationships.outgoing == {}


@pytest.mark.anyio
async def test_get_entity_without_relationships_key() -> None:
    seen: list[httpx2.Request] = []
    # 200 without rels
    transport = recording_transport(
        httpx2.Response(
            200,
            json={k: v for k, v in ENTITY_WITHOUT_RELATIONSHIPS.items() if k != "relationships"},
        ),
        seen,
    )

    async with CalaClient(api_key="test-key", timeout=5, transport=transport) as client:
        response = await client.get_entity(APPLE_ID)

    assert isinstance(response, EntityDetails)
