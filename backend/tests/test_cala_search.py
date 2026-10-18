"""Cala knowledge search (POST /v1/knowledge/search): request, typed answer, retries."""

import json

import httpx2
import pytest

from market_desk.clients.cala import CalaClient, SearchAnswer

QUESTION = "Who is Apple's CEO?"

# A realistic answer, shaped like Cala's `Answer` schema (explainability left out on purpose)
ANSWER_BODY = {
    "content": "Tim Cook has been Apple's CEO since August 2011.",
    "context": [
        {
            "id": "3f1c2b9a-6c1d-4a51-9f0e-2a7d1b3c4e5f",
            "content": "Tim Cook became CEO of Apple Inc. on August 24, 2011.",
            "origins": [
                {
                    "source": {"name": "SEC EDGAR", "url": "https://www.sec.gov"},
                    "document": {
                        "name": "Apple Inc. Form 8-K (2011-08-24)",
                        "url": "https://www.sec.gov/Archives/edgar/data/320193/example.htm",
                    },
                    "breadcrumb": ["Apple Inc.", "Leadership"],
                }
            ],
        }
    ],
    "entities": [
        {
            "id": "e5bb591a-d308-4aa5-9672-96046d366cde",
            "name": "Apple Inc.",
            "entity_type": "Company",
            "mentions": ["Apple"],
        }
    ],
}
RATE_LIMIT_BODY = {"error": "rate_limit_exceeded", "message": "Rate limit exceeded."}


def scripted_transport(
    responses: list[httpx2.Response], seen: list[httpx2.Request]
) -> httpx2.MockTransport:
    """A fake Cala that records each request and answers with the next response, in order."""
    remaining = iter(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return next(remaining)

    return httpx2.MockTransport(handler)


class FakeSleep:
    """Stands in for asyncio.sleep: records each wait and returns at once."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.mark.anyio
async def test_search_sends_post_with_json_body() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # 200
    transport = scripted_transport(
        [
            httpx2.Response(200, json=ANSWER_BODY),
        ],
        seen,
    )

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        await client.search(QUESTION)

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert request.url.host == "api.cala.ai"
    assert request.url.path == "/v1/knowledge/search"
    assert json.loads(request.content) == {
        "input": QUESTION,
        "explainability": False,
        "return_entities": True,
    }


@pytest.mark.anyio
async def test_search_returns_typed_answer_with_sources() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # 200
    transport = scripted_transport(
        [
            httpx2.Response(200, json=ANSWER_BODY),
        ],
        seen,
    )

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        answer = await client.search(QUESTION)

    assert isinstance(answer, SearchAnswer)
    assert "Tim Cook" in answer.content
    assert answer.context[0].origins[0].source.name == "SEC EDGAR"
    assert (
        answer.context[0].origins[0].document.url
        == "https://www.sec.gov/Archives/edgar/data/320193/example.htm"
    )
    assert answer.entities is not None
    assert answer.entities[0].name == "Apple Inc."


@pytest.mark.anyio
async def test_search_with_null_entities() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # 200
    transport = scripted_transport(
        [
            httpx2.Response(200, json={**ANSWER_BODY, "entities": None}),
        ],
        seen,
    )

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        answer = await client.search(QUESTION)

    assert isinstance(answer, SearchAnswer)
    assert answer.entities is None


@pytest.mark.anyio
async def test_search_429_then_200_is_retried() -> None:
    seen: list[httpx2.Request] = []
    fake_sleep = FakeSleep()
    # 429 + 200
    transport = scripted_transport(
        [
            httpx2.Response(429, json=RATE_LIMIT_BODY, headers={"retry-after": "1"}),
            httpx2.Response(200, json=ANSWER_BODY),
        ],
        seen,
    )

    async with CalaClient(
        api_key="test-key", timeout=5, transport=transport, sleep=fake_sleep
    ) as client:
        answer = await client.search(QUESTION)

    assert isinstance(answer, SearchAnswer)
    assert len(seen) == 2
    assert fake_sleep.calls == [1.0]
