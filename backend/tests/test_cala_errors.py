"""Cala client error mapping: every failure becomes a CalaError subclass, never a raw httpx2 error.

Rule under test: the status code decides the exception; the body only adds detail.
"""

import httpx2
import pytest

from market_desk.clients.cala import (
    CalaClient,
    CalaError,
    CalaRateLimitError,
    CalaResponseError,
    CalaServerError,
    CalaValidationError,
    Entity,
)

# Bodies as Cala's OpenAPI spec documents them (two different error shapes)
VALIDATION_ERROR_BODY = {
    "response_type": "ERROR",
    "error": {"error_type": "search_query_error", "message": "Invalid query"},
}
RATE_LIMIT_BODY = {
    "error": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Too many requests.",
}
# What a proxy or load balancer in front of Cala might send instead of JSON
HTML_BODY = "<html><body><h1>502 Bad Gateway</h1></body></html>"


async def search_with(response: httpx2.Response) -> list[Entity]:
    """Call search_entities against a fake Cala that always answers with `response`."""
    transport = httpx2.MockTransport(lambda request: response)
    async with CalaClient(api_key="test-key", timeout=5, transport=transport) as client:
        return await client.search_entities("Apple")


# --- 422: the request is invalid; never retried ---


@pytest.mark.anyio
async def test_422_raises_validation_error_with_type_and_message() -> None:
    response = httpx2.Response(422, json=VALIDATION_ERROR_BODY)

    with pytest.raises(CalaValidationError) as exc_info:
        await search_with(response)

    assert exc_info.value.error_type == "search_query_error"
    assert exc_info.value.message == "Invalid query"


@pytest.mark.anyio
async def test_422_with_non_json_body_is_still_a_validation_error() -> None:
    response = httpx2.Response(422, text=HTML_BODY)

    with pytest.raises(CalaValidationError) as exc_info:
        await search_with(response)

    assert exc_info.value.error_type == "unknown"
    assert "502 Bad Gateway" in exc_info.value.message


@pytest.mark.anyio
async def test_422_with_unexpected_json_shape_is_still_a_validation_error() -> None:
    response = httpx2.Response(422, json={"detail": "something else"})

    with pytest.raises(CalaValidationError) as exc_info:
        await search_with(response)

    assert exc_info.value.error_type == "unknown"


# --- 429: too many requests; retried in step 3 using retry_after ---


@pytest.mark.anyio
async def test_429_raises_rate_limit_error_with_retry_after() -> None:
    response = httpx2.Response(429, json=RATE_LIMIT_BODY, headers={"retry-after": "2"})

    with pytest.raises(CalaRateLimitError) as exc_info:
        await search_with(response)

    assert exc_info.value.retry_after == 2.0
    assert exc_info.value.message == "Rate limit exceeded. Too many requests."


@pytest.mark.anyio
async def test_429_without_retry_after_header() -> None:
    response = httpx2.Response(429, json=RATE_LIMIT_BODY)

    with pytest.raises(CalaRateLimitError) as exc_info:
        await search_with(response)

    assert exc_info.value.retry_after is None
    assert exc_info.value.message == "Rate limit exceeded. Too many requests."


@pytest.mark.anyio
async def test_429_with_non_numeric_retry_after_means_unknown() -> None:
    response = httpx2.Response(429, json=RATE_LIMIT_BODY, headers={"retry-after": "soon"})

    with pytest.raises(CalaRateLimitError) as exc_info:
        await search_with(response)

    assert exc_info.value.retry_after is None


@pytest.mark.anyio
async def test_429_with_non_json_body_is_still_a_rate_limit_error() -> None:
    # Must stay a CalaRateLimitError: that's the type step 3 retries
    response = httpx2.Response(429, text=HTML_BODY, headers={"retry-after": "1"})

    with pytest.raises(CalaRateLimitError) as exc_info:
        await search_with(response)

    assert exc_info.value.retry_after == 1.0


# --- 5xx and other 4xx ---


@pytest.mark.anyio
async def test_500_raises_server_error() -> None:
    response = httpx2.Response(500, text=HTML_BODY)

    with pytest.raises(CalaServerError):
        await search_with(response)


@pytest.mark.anyio
async def test_other_4xx_raises_base_cala_error() -> None:
    response = httpx2.Response(404, text=HTML_BODY)

    with pytest.raises(CalaError) as exc_info:
        await search_with(response)

    assert type(exc_info.value) is CalaError


# --- 200 with a body that isn't what we expect ---


@pytest.mark.anyio
async def test_200_with_non_json_body_raises_response_error() -> None:
    response = httpx2.Response(200, text=HTML_BODY)

    with pytest.raises(CalaResponseError):
        await search_with(response)


@pytest.mark.anyio
async def test_200_without_entities_key_raises_response_error() -> None:
    response = httpx2.Response(200, json={"results": []})

    with pytest.raises(CalaResponseError):
        await search_with(response)


@pytest.mark.anyio
async def test_200_with_invalid_entity_raises_response_error() -> None:
    response = httpx2.Response(
        200,
        json={
            "entities": [
                {
                    "description": "An American multinational technology company.",
                    "entity_type": "Company",
                    "id": "not-a-uuid",
                    "name": "OpenAI",
                }
            ]
        },
    )

    with pytest.raises(CalaResponseError):
        await search_with(response)
